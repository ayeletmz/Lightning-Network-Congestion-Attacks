from network_parser import *
from mpl_toolkits.axes_grid1.inset_locator import zoomed_inset_axes, mark_inset
import matplotlib.pyplot as plt
import numpy as np


"""
    This module simulates an attack on a single node in the Lightning Network, aiming to disconnect it from the rest of
    the network by paralyzing its adjacent channels for an extended period of time. The adversary connects to the
    victim with a new channel, initiates a payment to itself via a route that begins with its connection to the victim,
    traversing a single target channel back and forth multiple times. Repeating this multiple times exhausting the
    number of simultaneously open HTLCs the target channel allows, will lock it for new payments.
    We evaluate this attack by:
    1. Running it on N top capacity nodes in the network (one by one) and presenting results in logs.
    2. Running it on a LNBIG nodes as a group (holds ~ 50% of the network capacity (Jan 2020)), separating them
       from the rest of the network.
    3. Plotting Degree Analysis: running the attack on each node in the network and plotting the costs (number of 
       channels the attacker opens) per node by its degree.
    4. Plotting Implementation Analysis: we wish to give a degree analysis on a hypothetical network where all nodes run
       the same implementation (from LND\C-Lightning\Eclair). For each implementation we create new nodes having the
       corresponding implementation default values, with different degrees. We assume the neighbors of the victim node
       run the same implementation as it does. We attack these nodes and for each implementation plot the costs (number 
       of channels the attacker opens) per node by its degree.
"""


LOCKTIME_MAX = 144 * 14  # = 2016
MAX_ROUTE_LEN = 20
LOCK_PERIOD = 432  # 3 days


def _calc_num_of_payments(attacker_edge, target_edge):
    """
    Calculate the number of payments the attacker will initiate using its given edge for locking the target edge,
    considering the HTLC quotas restrictions on both edges.
    Returns the number of payments and the number target edge will be crossed sending them.
    """

    # num_target_edge_crossing = route length minus 2 = number of times we cross the target edge going the back and
    # forth on it.
    # attacker_edge['time_lock'] is set to the cltv delta of the target node in the attackers' channel (for the last
    # hop). target_edge['time_lock'] is set to the sum of cltv deltas of both nodes of this edge (for a single back and
    # forth transition).
    num_target_edge_crossing = min(
        int(np.floor((LOCKTIME_MAX - LOCK_PERIOD - attacker_edge['time_lock']) / target_edge['time_lock'])) * 2,
        MAX_ROUTE_LEN - 2)
    if num_target_edge_crossing == 0:
        # Cannot lock edge using back and forth strategy
        return 0, 0
    else:
        # Number of payments the attacker will send.
        num_of_payments = int(np.floor(target_edge['htlc'] / num_target_edge_crossing))
        if target_edge['htlc'] % num_target_edge_crossing:
            num_of_payments += 1
        num_attacker_possible_payments = int(np.floor(attacker_edge['htlc'] / 2))
        num_of_payments = min(num_of_payments, num_attacker_possible_payments)

    total_target_edge_crossing = num_of_payments * num_target_edge_crossing
    return num_of_payments, total_target_edge_crossing


def _attack_edge(attacker_edge, target_edge):
    """
    Attacker sends the maximum number of payments in order to lock the target channel using its given edge.
    Returns True iff at least one payment was sent. The case of False is when it is not possible to attack the edge
    using back and forth strategy.
    """
    num_of_payments, total_target_edge_crossing = _calc_num_of_payments(attacker_edge, target_edge)
    if num_of_payments == 0:
        logger.warning('Cannot attack edge ' + str(target_edge['channel_id']) +
                     ". Cltv deltas are too large, hence it is not possible to traverse back and forth this edge.")
        return False
    target_edge['htlc'] -= total_target_edge_crossing
    attacker_edge['htlc'] -= num_of_payments * 2
    return True


def attack_node(G, node, alias=None):
    """
    Given a target node, the attacker connects to it and paralyzes its adjacent channels one by one sending payments
    going back and forth on these channels.
    """
    G = G.copy()
    neighbours = G.adj[node]._atlas
    adjacent_channels = [neighbours[adj_node_id][channel_id] for adj_node_id in neighbours for channel_id in
                         neighbours[adj_node_id]]
    num_adjacent_channels = len(adjacent_channels)
    alias = G.nodes(data=True)[node]['alias'] if alias is None else alias

    if num_adjacent_channels == 0:
        logger.info("Node [" + alias + ":" + node + "] is already isolated.")
        return 0

    total_attacked_capacity = sum([c['capacity'] for c in adjacent_channels])
    logger.info("["+alias+"] Attacking node " + node + ". Degree: " + str(num_adjacent_channels) + ", Capacity: " +
                str(round(total_attacked_capacity / 1e8, 1)) + " BTC (" +
                str(round(total_attacked_capacity * 100 / G.graph['network_capacity'], 1)) +
                "% of the network).")

    # Add attacker node
    G.add_node("0" * 66)

    #  Attacker opens a channel with the target node. It sets the channels' attributes to fit the attack according to
    # the target node implementation.
    node_cltv_delta = CLTV_DELTA_DEFAULTS[G.nodes()[node]['implementation']]
    # The attacker is restricted in sending requests to the target node in accordance with the nodes' max_htlc.
    attacker_max_htlc = MAX_CONCURRENT_HTLCS_DEFAULTS[G.nodes()[node]['implementation']]
    attacker_edge_key = node + "-" + str(G.number_of_edges("0" * 66, node))
    G.add_edge("0" * 66, node, attacker_edge_key, htlc=attacker_max_htlc, Attacker=True,
               node1_pub="0" * 66, node2_pub=node, channel_id=attacker_edge_key, time_lock=node_cltv_delta)

    attacker_edge = G.edges["0" * 66, node, attacker_edge_key]

    while adjacent_channels:  # iterate the adjacent channels and lock them one by one

        # If the attacker exhausted the quota of HTLCs it can hold, he opens a new channel.
        if attacker_edge['htlc'] <= 1:
            attacker_edge_key = node + "-" + str(G.number_of_edges("0" * 66, node))
            G.add_edge("0" * 66, node, attacker_edge_key, htlc=attacker_max_htlc, Attacker=True,
                       node1_pub="0" * 66, node2_pub=node, channel_id=attacker_edge_key, time_lock=node_cltv_delta)
            attacker_edge = G.edges["0" * 66, node, attacker_edge_key]

        # Attack the first available (not locked) target node channel.
        if not _attack_edge(attacker_edge, adjacent_channels[0]):
            #  If channel cannot be attacked using back and forth strategy, move to the next channel.
            adjacent_channels = adjacent_channels[1:]
        #  If target channel was fully locked (or remain with 1 HTLC quota)
        if adjacent_channels[0]['htlc'] <= 1:
            adjacent_channels = adjacent_channels[1:]
        #  Leftovers of 1 HTLCs and channels that cannot be attacked back and forth but can in one direction,
        #  can be handled by passing one direction payments through them in order to fully lock them.

    attacked_channels = \
        list(filter(lambda x: x["htlc"] <= 1, [i[2] for i in G.edges(data=True) if not i[2]['Attacker']]))
    locked_capacity = sum(list(map(lambda x: x['capacity'], attacked_channels)))
    num_attacker_channels = G.number_of_edges("0" * 66, node)
    logger.info("["+alias+"] Succeeded to attack " + str(len(attacked_channels)) +
                " out of " + str(num_adjacent_channels) + " adjacent channels.")
    logger.info("["+alias+"] Attacker needed to open " +
                str(num_attacker_channels) + " channels for the attack. It locked " +
                str(round(locked_capacity / G.graph['network_capacity'] * 100, 1))
                + "% of the network capacity for " + str(round(LOCK_PERIOD / 144, 1)) + " days.")
    # We still have leftovers of 1 HTLCs in channels if the node runs LND implementation. The attacker too has this
    # leftovers on its channels, it can open few more channels in strategic locations - where in creates short
    # paths between many of the target channels and then perform circular one direction routes passing through these
    # channels and fully lock them.

    # Return (number of attacker channels, number of attacked channels, capacity locked)
    return num_attacker_channels, len(attacked_channels), locked_capacity


def _remove_intra_edges(G, nodes):
    """
    Remove channels connecting the given nodes.
    """
    all_pairs = list()  # all pairs of nodes
    for p1 in range(len(nodes)):
        for p2 in range(p1 + 1, len(nodes)):
            all_pairs.append([nodes[p1], nodes[p2]])
    # num_intra_edges = len([edge_key for node1, node2 in all_pairs for edge_key in list(G.adj[node1]._atlas[node2])])
    for node1, node2 in all_pairs:  # for each pair of nodes
        if node2 in G.adj[node1]._atlas:
            for edge_key in list(G.adj[node1]._atlas[node2]):  # for each edge between this pair
                edge = G.adj[node1]._atlas[node2][edge_key]
                G.remove_edge(edge['node1_pub'], edge['node2_pub'], key=edge['channel_id'])  # remove edge from graph


def _get_channels_connected_to_nodes_info(G, nodes):
    """
    Returns a list of all channels connected to at least one node from the given list.
    """
    channels = list()
    for node in nodes:
        neighbours = G.adj[node]._atlas
        channels += [channel for adj_node_id in neighbours for channel in neighbours[adj_node_id].items()]
    # Remove duplications
    seen = set()
    channels = [(a, b) for a, b in channels if not (a in seen or seen.add(a))]
    num_of_channels = len(channels)
    capacity = sum([channel[1]['capacity'] for channel in channels])
    return num_of_channels, capacity


def _isolate_group_of_nodes(G, nodes, alias=None):
    """
    Isolate a set of nodes from the network
    """
    G = G.copy()
    num_of_channels, capacity = _get_channels_connected_to_nodes_info(G, nodes)
    logger.info("["+alias+"] Attacking " + str(len(nodes)) + " nodes, having " + str(num_of_channels) +
                " channels with a total capacity of " + str(round(capacity / 1e8, 1)) + " BTC (" +
                str(round(capacity * 100 / G.graph['network_capacity'], 1)) + "% of the network).")

    # Remove all edges between given nodes (we want to attack only the inter edges).
    _remove_intra_edges(G, nodes)
    num_of_channels, capacity = _get_channels_connected_to_nodes_info(G, nodes)
    logger.info("[" + alias + "] Attacking " + str(num_of_channels) +
                " channels (without the intra edges), which hold total capacity of " + str(round(capacity / 1e8, 1)) +
                " BTC (" + str(round(capacity * 100 / G.graph['network_capacity'], 1)) + "% of the network).")
    total_num_attacker_channels = 0
    total_num_attacked_channels = 0
    total_locked_capacity = 0
    for node in nodes:
        num_attacker_channels, num_attacked_channels, locked_capacity = attack_node(G, node)
        total_num_attacker_channels += num_attacker_channels
        total_num_attacked_channels += num_attacked_channels
        total_locked_capacity += locked_capacity
    logger.info("[" + alias + "] Attacker needed to open " +
                str(total_num_attacker_channels) + " channels for the attack. It locked " + str(total_num_attacked_channels) +
                " channels with " + str(round(total_locked_capacity / G.graph['network_capacity'] * 100, 1))
                + "% of the network capacity for " + str(round(LOCK_PERIOD / 144, 1)) + " days.")


def attack_selected_hubs(snapshot_path):
    """
     We run the attack on the 10 top capacity nodes in the network (one by one), isolating them from the network.
     In addition, we attack LNBIG nodes as a group, separating them from the rest of the network.
     All results are printed to logs.
    """
    # Read json file created by LND describegraph command on the mainnet.
    json_data = load_json(snapshot_path)
    # Parse data into a networkx MultiGraph obj.
    G = load_graph(json_data)
    # Removing edges that cannot be attacked due to a capacity lower than the dust limit * max concurrent htlcs.
    remove_below_dust_capacity_channels(G)
    # nodes sorted by decreasing capacity
    nodes = sorted(G.nodes(data=True), key=lambda x: x[1]['capacity'], reverse=True)
    # Attacking 10 top capacity hubs.
    for node in nodes[:10]:
        if node[1]['alias'] == '03021c5f5f57322740e4':
            attack_node(G, node[0], "BlueWallet")
        else:
            attack_node(G, node[0])
    # Attacking LNBIG - a set of nodes controlled by a single entity. We isolate them from the rest of the network.
    LNBIG_nodes = [node[0] for node in list(filter(lambda x: x[1].get('alias').startswith('LNBIG.com [lnd-'), nodes))]
    _isolate_group_of_nodes(G, LNBIG_nodes, "LNBIG nodes")


def plot_degree_analysis(snapshot_path):
    """
    An evaluation of the cost of attack on all nodes in the network using a given snapshot, isolating each node for
    LOCK_PERIOD days. We plot an histogram of the degree of nodes, and a graph that shows the relation between the
    degree and the number of channels channels that the attacker needs to open in order to perform the attack on
    each node.
    """
    logger.info("Attack on Hub: Running Degree Analysis")
    # Read json file created by LND describegraph command on the mainnet.
    json_data = load_json(snapshot_path)
    # Parse data into a networkx MultiGraph obj.
    G = load_graph(json_data)

    # Removing edges that cannot be attacked due to a capacity lower than the dust limit * max concurrent htlcs.
    remove_below_dust_capacity_channels(G)
    G.remove_nodes_from(list(nx.isolates(G)))

    nodes = G.nodes(data=True)
    fig, (ax2, ax1) = plt.subplots(2, figsize=(10, 8))

    ####### Histogram of degrees of nodes in the network ######
    degrees = [G.degree(node[0]) for node in nodes]
    ax1.set_xlim((0, 54))
    ax1.hist(degrees, bins=np.arange(1, 52, 2), weights=[1 / len(degrees)] * len(degrees), align="left")
    greater_than_50 = sum(1 for i in degrees if i > 50) / len(degrees)
    ax1.bar(52, greater_than_50, width=2)
    ax1.text(51.4, -0.041, "51+", fontsize=16)
    ax1.set_xlabel('Degree', fontsize=16)
    ax1.set_xticks(np.arange(0, 60, 10))
    ax1.set_xticklabels(labels=np.arange(0, 60, 10), fontsize=16)
    ax1.set_ylabel('Fraction of nodes', fontsize=18)
    ax1.set_yticks(np.arange(0, 0.45, 0.05))
    ax1.set_yticklabels(labels=["{:.2f}".format(x) for x in np.arange(0, 0.45, 0.05)], fontsize=16)
    ax1.set_title("Histogram of degrees of nodes in the network", fontsize=19)

    logger.debug("Average Degree: " + str(np.average(degrees)) + ", Std: " + str(np.std(degrees)) +
                 ", Max Degree: " + str(max(degrees)))
    logger.debug(str(round(sum(1 for i in degrees if i < 15) * 100 / len(degrees), 1)) +
                 "% of the nodes are of degree < 15")
    logger.debug(str(round(sum(1 for i in degrees if i > 50) * 100 / len(degrees), 1)) +
        "% of the nodes are of degree > 50")
    logger.debug(str(round(sum(1 for i in degrees if i > 500) * 100 / len(degrees), 2)) +
                 "% of the nodes are of degree > 500")

    ####### Channels required in order to isolate nodes of different degrees ######
    # We plot the relation between the degree and the number of channels the attacker needs to open in order to perform
    # the attack on each node. Each node will be represented by a point in the graph. The number of channels is not
    # directly determined by the degree, because different nodes set up  different values of cltv deltas.
    attack_cost_by_degree = dict()
    for node in nodes:
        degree = G.degree(node[0])
        if not degree in attack_cost_by_degree.keys():
            attack_cost_by_degree[degree] = list()
        attack_cost_by_degree[degree].append(attack_node(G, node[0])[0])
    for degree in sorted(attack_cost_by_degree.keys()):
        for node_result in attack_cost_by_degree[degree]:
            ax2.scatter(degree, node_result, s=16, color="#4C72B0", alpha=0.5, edgecolors='none')
    ax2.set_xlabel('Degree', fontsize=18)
    ax2.set_xticks(np.arange(0, 650, 100))
    ax2.set_xticklabels(labels=np.arange(0, 650, 100), fontsize=16)
    ax2.set_ylabel('Attacker Channels', fontsize=18)
    ax2.set_yticks(np.arange(0, 120, 20))
    ax2.set_yticklabels(labels=np.arange(0, 120, 20), fontsize=16)
    ax2.set_xlim((0, 650))
    ax2.set_ylim((0, 105))
    ax2.set_title("Channels required in order to isolate nodes of different degrees", fontsize=19)
    plt.tight_layout()
    plt.savefig("plots/attack_on_hub_degree_analysis.svg")


def _add_node(G, implementation, degree):
    """
    Adds to the graph a new node that initializes to the default values corresponding to the input implementation,
    and opens channels to it according to the given degree.
    """
    node = implementation + "-" + str(degree)
    G.add_node(node, implementation=implementation, alias=node)

    neighbour = G.add_node("neighbour", implementation=implementation, alias="neighbour-" + node)

    for i in range(degree):  # Since it is a multigraph, we can add #degree edges to the same neighbour.
        channel_id = node + "-" + str(i)
        G.add_edge(node, neighbour, channel_id, htlc=MAX_CONCURRENT_HTLCS_DEFAULTS[implementation],
                   Attacker=False, node1_pub=node, node2_pub=neighbour, channel_id=channel_id,
                   time_lock=2 * CLTV_DELTA_DEFAULTS[implementation], capacity=0)
    return node


def plot_implementation_analysis():
    """
    Estimates the cost of isolating nodes running one of the major implementations, assuming default values are used
    by it and its neighbors. We calculate the number of channels the attacker needs to open in order to isolate a node
    for LOCK_PERIOD days for different degrees.
    """
    logger.info("Attack on Hub: Running Implementation Analysis")
    # Initiate a new networkx MultiGraph obj.
    G = nx.MultiGraph()
    G.graph['network_capacity'] = 1
    # A dictionary that holds for each implementation a list of the number of channels the attacker needs to open in
    # order to attack nodes of each degree.
    results_by_impl = dict()
    max_degree = 520
    for implementation in IMPLEMENTATIONS:
        results_by_impl[implementation] = list()
        for degree in range(1, max_degree):
            node = _add_node(G, implementation, degree)
            results_by_impl[implementation].append(attack_node(G, node)[0])

    fig, ax = plt.subplots(figsize=(5, 4))
    for implementation in results_by_impl.keys():
        ax.plot(np.arange(max_degree), [0] + results_by_impl[implementation], '-')
    plt.legend(results_by_impl.keys(), loc='lower right')
    plt.xlabel('Degree', fontsize=11)
    plt.ylabel('Attacker Channels', fontsize=11)
    plt.xlim((-20, 520))
    plt.ylim((-5, 103))
    axins = zoomed_inset_axes(ax, 10, loc=2)
    for implementation in results_by_impl.keys():
        axins.plot(np.arange(max_degree), [0] + results_by_impl[implementation], '.-')
    x1, x2, y1, y2 = -0.5, 20.5, -.2, 4.2  # specify the limits
    axins.set_xlim(x1-1, x2+1)  # apply the x-limits
    axins.set_ylim(y1-0.1, y2 + 0.1)  # apply the y-limits
    plt.yticks(visible=False)
    plt.xticks(visible=False)
    plt.text(0, -0.1, "0", fontsize=6)
    plt.text(9, -0.1, "10", fontsize=6)
    plt.text(19, -0.1, "20", fontsize=6)
    plt.text(0, 2, "2", fontsize=6)
    plt.text(0, 4, "4", fontsize=6)
    mark_inset(ax, axins, loc1=2, loc2=4, fc="none", ec="0.5", lw=0.5)
    plt.savefig("plots/attack_on_hub_implementation_analysis.svg")


def main():

    coloredlogs.install(fmt='%(asctime)s [%(module)s: line %(lineno)d] %(levelname)s %(message)s',
                        level=logging.DEBUG, logger=logger)

    snapshot_path = 'snapshots/LN_2020.09.21-08.00.01.json'

    attack_selected_hubs(snapshot_path)
    plot_degree_analysis(snapshot_path)
    plot_implementation_analysis()


if __name__ == "__main__":
    main()
