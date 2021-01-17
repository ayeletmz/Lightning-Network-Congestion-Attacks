import json
from networkx_changes.node_link import node_link_graph
import networkx as nx
from lightning_implementation_inference import infer_node_implementation
import copy
import coloredlogs
import logging
import seaborn as sns


"""
    This module parses a Lightning Network snapshot (generated by using LND's describegraph command) into a convenient
    object to work with (analyze data and simulate attacks), represented as a NetworkX multigraph.
"""

########### Logs and Plots Styles\Settings ###############
sns.set()
sns.set_style(style='whitegrid')
coloredlogs.DEFAULT_LEVEL_STYLES['info'] = dict(color='blue')
coloredlogs.DEFAULT_FIELD_STYLES['asctime'] = dict(color="magenta")
logger = logging.getLogger('lightning_congestion')
######################################################

EPSILON = 1e-6
IMPLEMENTATIONS = ['LND', 'C-Lightning', 'Eclair']
MAX_CONCURRENT_HTLCS_DEFAULTS = {"LND": 483, 'C-Lightning': 30, 'Eclair': 30}
CLTV_DELTA_DEFAULTS = {'LND': 40, 'C-Lightning': 14, 'Eclair': 144}
DEFAULT_DUST_LIMIT_SAT = 546  # in sat


def load_json(snapshot_path):
    # Read json file created by LND describegraph command on the mainnet.
    f = open(snapshot_path, 'r', encoding="utf8")
    json_data = json.load(f)

    for channel in json_data['edges']:
        _cast_channel_data(channel)
    return json_data


def _cast_channel_data(channel):
    # Convert numeric parameter values (integers) that are held as strings to their natural form (int).
    channel['capacity'] = int(channel['capacity'])
    if channel['node1_policy']:
        channel['node1_policy']['min_htlc'] = int(channel['node1_policy']['min_htlc'])
        channel['node1_policy']['fee_base_msat'] = int(channel['node1_policy']['fee_base_msat'])
        channel['node1_policy']['fee_rate_milli_msat'] = int(channel['node1_policy']['fee_rate_milli_msat'])
    if channel['node2_policy']:
        channel['node2_policy']['min_htlc'] = int(channel['node2_policy']['min_htlc'])
        channel['node2_policy']['fee_base_msat'] = int(channel['node2_policy']['fee_base_msat'])
        channel['node2_policy']['fee_rate_milli_msat'] = int(channel['node2_policy']['fee_rate_milli_msat'])


def filter_snapshot_data(json_data):
    # Filter to channels having both peers exposing their policies
    json_data['edges'] = list(filter(lambda x: x['node1_policy'] and x['node2_policy'], json_data['edges']))
    # Filter to non disabled channels
    json_data['edges'] = list(filter(lambda x: not (x['node1_policy']['disabled'] or x['node2_policy']['disabled']),
                                     json_data['edges']))
    return json_data


def _calc_edges_timelock(G):
    # For each edge calculates the sum of time_lock_delta values on both peers.
    # (This value will be used when attacking edges back and forth - hence using both peers time_lock_delta)
    edges_timelock_dict = dict.fromkeys(G.edges, 0)
    for key in edges_timelock_dict:
        edge = G.edges[key]
        edges_timelock_dict[key] = edge['node1_policy']['time_lock_delta'] + edge['node2_policy']['time_lock_delta']
    return edges_timelock_dict


def _calc_edges_betweenness(G):
    # For each edge calculates the betweenness.
    edge_betweenness = dict.fromkeys(G.edges, 0)
    edge_betweenness_by_pair_of_nodes = nx.edge_betweenness_centrality(G)
    for key in edge_betweenness:
        edge_betweenness[key] = edge_betweenness_by_pair_of_nodes[key[:2]]
    ### G.edges[list(G.edges)[0]]['betweenness']
    return edge_betweenness


def update_edges_betweenness(G):
    nx.set_edge_attributes(G, _calc_edges_betweenness(G), ' betweenness')


def _calc_node_capacity(G, node):
    """
    Returns node's total capacity (sum of the capacities on its adjacent edges)
    """
    neighbours = G.adj[node]._atlas
    return sum([neighbours[adj_node_id][channel_id]['capacity'] for adj_node_id in neighbours for channel_id in
                neighbours[adj_node_id]])


def _handle_unknown_impl_nodes(G):
    """
    Almost always, the implementation inference manages to match an implementation to each node - meaning no node is
    tagged as 'unknown'. For the cases were the are such nodes, we first verify their negligence, meaning they make up
    less than 0.5% of the nodes, and that their sum of capacities are less than 0.05% of the networks'. Then we
    remove them.
    """
    unknown_impl_nodes = list(filter(lambda x: x[1]['implementation'] == 'unknown', G.nodes(data=True)))
    if unknown_impl_nodes:
        assert len(unknown_impl_nodes) / G.number_of_nodes() < 0.005 and \
                sum([node[1]['capacity'] for node in unknown_impl_nodes]) / G.graph['network_capacity'] < 0.0005
        G = _remove_nodes(G, [node[0] for node in unknown_impl_nodes])
        G.graph['network_capacity'] = sum(list(map(lambda x: x[2]['capacity'], G.edges(data=True))))
        G.graph['network_channels_count'] = nx.number_of_edges(G)
        # Sets 'capacity' attribute for nodes
        nx.set_node_attributes(G, {node: _calc_node_capacity(G, node) for node in G.nodes}, 'capacity')
    return G


def _edges_max_concurrent_htlcs(G):
    # Assigns each channel the htlc quota initialized to the default MAX_CONCURRENT_HTLCS according
    # to the inferred implementation.
    return {key: min(MAX_CONCURRENT_HTLCS_DEFAULTS[G.nodes[G.edges[key]['node1_pub']]['implementation']],
                     MAX_CONCURRENT_HTLCS_DEFAULTS[G.nodes[G.edges[key]['node2_pub']]['implementation']])
            for key in G.edges.keys()}


def load_graph(json_data):
    # Remove channels that are disabled or that do not declare their policies.
    json_data = filter_snapshot_data(json_data)
    # Create an undirected multigraph using networkx
    G = node_link_graph(json_data, False, True,
                        {'name': 'pub_key', 'source': 'node1_pub', 'target': 'node2_pub', 'key': 'channel_id',
                         'link': 'edges', 'network_capacity': 0, 'network_channels_count': 0})
    # Remove isolated nodes
    G.remove_nodes_from(list(nx.isolates(G)))
    # Sets a new attribute 'Attacker' to each edge, initialized to False. Edges that will be added in order to simulate
    # attacks will be tagged True.
    nx.set_edge_attributes(G, False, 'Attacker')
    # Graph capacity (without attack intervention)
    G.graph['network_capacity'] = sum(list(map(lambda x: x[2]['capacity'], G.edges(data=True))))
    # Number of channels in the network graph (without attack intervention)
    G.graph['network_channels_count'] = nx.number_of_edges(G)
    # Sets 'time_lock' attribute to each edge, which holds the sum of time_lock_delta values on both sides
    nx.set_edge_attributes(G, _calc_edges_timelock(G), 'time_lock')
    # Sets 'capacity' attribute for nodes
    nx.set_node_attributes(G, {node: _calc_node_capacity(G, node) for node in G.nodes}, 'capacity')
    # Sets 'implementation' attribute for nodes
    nx.set_node_attributes(G, {node: infer_node_implementation(G, node) for node in G.nodes}, 'implementation')
    # Sets 'betweenness' attribute to each edge
    nx.set_edge_attributes(G, _calc_edges_betweenness(G), 'betweenness')
    G = _handle_unknown_impl_nodes(G)
    # Sets 'htlc' attribute to each edge, initialized to the default max_concurrent_htlcs according to the
    # inferred implementation. This attribute indicates the remaining quota of htlcs that the peer will accept.
    nx.set_edge_attributes(G, _edges_max_concurrent_htlcs(G), 'htlc')
    return G


def remove_below_dust_capacity_channels(G):
    """
    Removes edges from G with capacity lower than the dust limit * max concurrent htlcs.
    """
    removed_capacity = 0
    for edge in copy.deepcopy(G.edges(data=True)):
        edge_data = edge[2]
        if edge_data['capacity'] < edge_data['htlc'] * DEFAULT_DUST_LIMIT_SAT:
            removed_capacity += edge_data['capacity']
            G.remove_edge(edge_data['node1_pub'], edge_data['node2_pub'], key=edge_data['channel_id'])
    logger.debug("Removing edges that cannot be attacked due to a capacity lower than the dust limit * max concurrent htlcs. "
                 "These constitute " + str(round(removed_capacity * 100 / G.graph['network_capacity'], 1))
                 + "% of the networks' capacity")


def _remove_edges(G, edges):
    """
    Removes the input edges from G and the remaining isolated nodes.
    """
    G_sub = copy.deepcopy(G)
    for edge in edges:
        if G_sub.has_edge(edge['node1_pub'], edge['node2_pub'], key=edge['channel_id']):
            G_sub.remove_edge(edge['node1_pub'], edge['node2_pub'], key=edge['channel_id'])
    G_sub.remove_nodes_from(list(nx.isolates(G_sub)))
    return G_sub


def _remove_nodes(G, nodes):
    """
    Removes the input nodes from G, including their edges and remaining isolated nodes.
    """
    G_sub = copy.deepcopy(G)
    for node in nodes:
        neighbours = G.adj[node]._atlas
        adjacent_edges = [neighbours[adj_node_id][channel_id] for adj_node_id in neighbours
                          for channel_id in neighbours[adj_node_id]]
        for edge in adjacent_edges:
            if G_sub.has_edge(edge['node1_pub'], edge['node2_pub'], key=edge['channel_id']):
                G_sub.remove_edge(edge['node1_pub'], edge['node2_pub'], key=edge['channel_id'])
        G_sub.remove_node(node)
    G_sub.remove_nodes_from(list(nx.isolates(G_sub)))
    return G_sub


def _get_subgraph_by_implementation(G, implementation):
    # Returns G reduced to nodes running the input implementation
    nodes_to_remove = [i[0] for i in list(G.nodes(data=True)) if i[1]['implementation'] != implementation]
    G_sub = _remove_nodes(G, nodes_to_remove)
    logger.debug("Subgraph reduced to " + implementation + " nodes holds " +
                 str(round(sum(list(map(lambda x: x[2]['capacity'], G_sub.edges(data=True))))
                           * 100 / G.graph['network_capacity'], 1)) + "% of the networks' capacity")
    return G_sub


def get_LND_subgraph(G):
    # Returns G reduced to LND nodes
    return _get_subgraph_by_implementation(G, 'LND')


def get_LND_complementary_subgraph(G):
    # Returns the complementary to the G reduced to LND nodes graph. This subgraph consists of all channels with at
    # least one Eclair or C-Lightning node.
    edges_to_remove = [e[2] for e in G.edges(data=True) if e[2]['htlc'] != 30]
    G_sub = _remove_edges(G, edges_to_remove)
    logger.debug("The complementary to LND subgraph holds " +
                 str(round(sum(list(map(lambda x: x[2]['capacity'], G_sub.edges(data=True))))
                           * 100 / G.graph['network_capacity'], 1)) + "% of the networks' capacity")
    return G_sub


def get_policy(channel, node_id):
    """
    Returns the policy for the given node in the given channel.
    """
    if node_id == channel['node1_pub']:
        return channel['node1_policy']
    elif node_id == channel['node2_pub']:
        return channel['node2_policy']
    raise Exception('Error: Node ' + node_id + ' is not a peer to channel ' + channel['channel_id'])
