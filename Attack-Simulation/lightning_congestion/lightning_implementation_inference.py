import numpy as np
from collections import Counter

"""
    This module performs implementation inference. 
    We consider the main three implementations of the Lightning Network protocol (BOLT) : LND, C-Lightning and Eclair. 
    We use the data nodes publish via channel_update messages in order to infer which implementation they run.
"""

IMPLEMENTATIONS = ['LND', 'C-Lightning', 'Eclair']

LND = (1, 0, 0)
C = (0, 1, 0)
ECLAIR = (0, 0, 1)

# Default parameter values as they appear in the different implementations (On January 2020)
CLTV_DELTA_DEFAULTS = {LND: [144, 40], C: [14], ECLAIR: [144]}
HTLC_MIN_DEFAULTS = {LND: [1000], C: [1000], ECLAIR: [1]}
FEE_DEFAULTS = {LND: [1], C: [10], ECLAIR: [100]}
# The weights used for each param in the classification. cltv_delta: 0.75, min_htlc: 0.2, fee_proportional: 0.05
PARAM_WEIGHTS_DIST = [0.75, 0.2, 0.05]


def get_keys_by_value(dict_of_elements, value_to_find):
    # Returns an indicator vector (array), the coordinate corresponds to the implementations.
    # For example the array [1,0,1] will be returned if value_to_find appeared in dict_of_elements item values that
    # correspond to LND and ECLAIR.
    list_of_keys = list()
    list_of_keys.append(np.array([0, 0, 0]))
    list_of_items = dict_of_elements.items()
    for item in list_of_items:
        if value_to_find in item[1]:
            list_of_keys.append(np.asarray(item[0]))
    return sum(list_of_keys)


def calc_implementation_distribution(sample):
    """
    Given a sample of (cltv_delta, min_htlc, fee_proportional) from a nodes' channel, we return a distribution on the
    implementations (indicating the probability to be running each).
    In case no inference can be made an array of zeros will be returned.
    """
    impl_vec = np.array([get_keys_by_value(CLTV_DELTA_DEFAULTS, sample[0]),
                         get_keys_by_value(HTLC_MIN_DEFAULTS, sample[1]),
                         get_keys_by_value(FEE_DEFAULTS, sample[2])])
    impl_dist = np.dot(PARAM_WEIGHTS_DIST, impl_vec)
    if not np.all(impl_dist == np.array([0, 0, 0])):
        impl_dist = impl_dist / sum(impl_dist)
    return impl_dist


def calc_node_attr(node, edge):
    """
    Returns a tuple of (cltv_delta, min_htlc, fee_proportional) values of the node in the channel.
    """
    policy = None
    if node == edge['node1_pub']:
        policy = edge['node1_policy']
    elif node == edge['node2_pub']:
        policy = edge['node2_policy']
    else:
        raise Exception('node ' + node + ' is not a peer to channel ' + edge['channel_id'])
    return policy['time_lock_delta'], policy['min_htlc'], policy['fee_rate_milli_msat']


def infer_node_implementation(G, node):
    """
    infers nodes' implementation (by its defaults).
    """
    neighbours = G.adj[node]._atlas
    # A list of tuples (cltv_delta, min_htlc, fee_proportional) values of the node for each of its channels.
    channels_parameteres = [calc_node_attr(node, neighbours[adj_node_id][channel_id]) for adj_node_id in
                          neighbours for channel_id in
                          neighbours[adj_node_id]]

    # A list of implementation distribution for each of the nodes' channel.
    channels_impl_dist = [calc_implementation_distribution(channel_params) for channel_params in channels_parameteres]
    impl_dist = sum(channels_impl_dist)
    if sum(impl_dist) != 0:
        impl_dist = impl_dist / sum(impl_dist)
        # Return the implementation with the highest inferred probability
        return IMPLEMENTATIONS[np.argmax(impl_dist)]
    else:
        return "unknown"

















#############################################################################################
# Simplistic heuristics to infer implementation. We used the above one, but this gave approximately the same
# results.
def infer_node_implementation_simple_heuristics(G, node):
    neighbours = G.adj[node]._atlas
    # A list of tuples (cltv_delta, min_htlc, fee_proportional) values of the node for each of its channels.
    channels_parameteres = [calc_node_attr(node, neighbours[adj_node_id][channel_id]) for adj_node_id in
                          neighbours for channel_id in
                          neighbours[adj_node_id]]
    # For each parameter, we sort the different values configured by the node in descending order (by their appearance).
    # These are represented as tuples (value, fraction) - which present each value with the fraction in which it is
    # configured by the node.
    cltv_delta = sorted(Counter([i[0] for i in channels_parameteres]).items(), key=lambda item: item[1], reverse=True)
    cltv_delta = list(map(lambda x: (x[0], x[1] / sum(j for i, j in cltv_delta)), cltv_delta))
    cltv_delta_values = [i[0] for i in cltv_delta]
    htlc_min = sorted(Counter([i[1] for i in channels_parameteres]).items(), key=lambda item: item[1], reverse=True)
    htlc_min = list(map(lambda x: (x[0], x[1] / sum(j for i, j in htlc_min)), htlc_min))
    fee_proportional = sorted(Counter([i[2] for i in channels_parameteres]).items(), key=lambda item: item[1], reverse=True)
    fee_proportional = list(map(lambda x: (x[0], x[1] / sum(j for i, j in fee_proportional)), fee_proportional))

    # cltv_delta[0][0] is the most common value of cltv_expiry_delta used by the node.
    if cltv_delta[0][0] == 14:
        return 'C-Lightning'
    if cltv_delta[0][0] == 40:
        return 'LND'
    if cltv_delta[0][0] == 144:
        # cltv_delta[1][0] is the second most common value of cltv_expiry_delta used by the node.
        if len(cltv_delta) > 1 and cltv_delta[1][0] == 40:
            return 'LND'
        if 40 in cltv_delta_values and cltv_delta[cltv_delta_values.index(40)][1] > 0.2:
            return 'LND'
        if htlc_min[0][0] == '1':
            return 'Eclair'
        if htlc_min[0][0] == '1000':
            return 'LND'
        if len(htlc_min) > 1 and htlc_min[0][1] == htlc_min[1][1]:
            if htlc_min[1][0] == '1000':
                return 'LND'
            if htlc_min[1][0] == '1':
                return 'Eclair'
        if fee_proportional[0][0] == '100':
            return 'Eclair'
        if fee_proportional[0][0] == '1':
            return 'LND'
    if 40 in cltv_delta_values and cltv_delta[cltv_delta_values.index(40)][1] > 0.2:
        return 'LND'
    if 14 in cltv_delta_values and cltv_delta[cltv_delta_values.index(40)][1] > 0.2:
        return 'C-Lightning'
    if htlc_min[0][0] == '1000':
        return 'LND'
    if htlc_min[0][0] == '1':
        return 'Eclair'
    return 'unknown'
##################################################################################################