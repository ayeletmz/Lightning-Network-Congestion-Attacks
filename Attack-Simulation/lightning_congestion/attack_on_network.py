from network_parser import *
from mpl_toolkits.axes_grid1.inset_locator import zoomed_inset_axes, mark_inset
import matplotlib.pyplot as plt
from os.path import isfile, join
from os import listdir
import numpy as np
import datetime
import operator

"""
    This module simulates an attack on the Lightning Network and evaluates the attack results.
    In the attack a malicious node uses a greedy algorithm in order to pick routes and paralyze as much liquidity
    as possible. It picks routes with high liquidity channels and with similar max_concurrent_htlcs. Routes which 
    fulfill the constraints of less than 20 hops and a maximum of locktime_max total delay. The attacker opens channels
    and initiates max_concurrent_htlcs payments (of minimal possible amounts) through each route. We evaluate the attack
    effectiveness and cost.
"""

LOCKTIME_MAX = 144 * 14  # = 2016
MIN_FINAL_CLTV_EXPIRY = 0
MAX_ROUTE_LEN = 20
OPEN_CHANNEL_COST_BTC = 0.00014  # corresponds to ~ 1 USD
MIN_CHANNEL_CAPACITY_BTC = 2e-5  # = 2000 sat


class Route:
    """
    Holds details regarding a route to be attacked.
    """
    def __init__(self, first_node, last_node, edges, time_lock, capacity, betweenness):
        self.first_node = first_node  # First intermediate node (not attackers').
        self.last_node = last_node  # Last intermediate node (not attackers').
        self.edges = edges  # Intermediate edges (not include attackers' first and last channels).
        self.time_lock = time_lock  # The number of blocks the route will be locked.
        self.capacity = capacity  # Does not include attackers'.
        self.betweenness = betweenness  # Does not include attackers'. First edge in route betweenness (while removed)
        self.policies = list()  # of intermediate nodes (all except the attacker). Relevant for cltv delta and fee calculations

    def len(self):
        return len(self.edges) + 2 # 2 (first and last edges) are attackers'


class AttackRoutes:
    """
    The attack results with a list of disjoint routes (in the order they've been chosen).
    This class holds the data for each route (potentially to be attacked).
    """

    def __init__(self):

        # Holds each route edges
        self.edges = list()

        # Holds each route length
        self.lengths = list()

        # Holds each route lock time
        self.lock_times = list()

        # Holds each route capacity (sum of capacities along its' channels)
        self.capacities = list()

        # Holds the payment amount (in msat) sent (by the first node - the attacker) in each route
        # (includes the fees)
        self.amounts_sent = list()

        # Holds the payment amount (in msat) received (by the last node - the attacker) in each route
        self.amounts_received = list()

        # Holds each route max_htlc - equals to the max_htlc value of all channels along it (30 or 483)
        self.max_htlcs = list()

        # Holds each route first edge betweenness (when removed)
        self.betweenness = list()


    @classmethod
    def combine(cls, attack_routes1, attack_routes2):
        attack_routes = cls()
        attack_routes.edges += attack_routes1.edges + attack_routes2.edges
        attack_routes.lengths += attack_routes1.lengths + attack_routes2.lengths
        attack_routes.lock_times += attack_routes1.lock_times + attack_routes2.lock_times
        attack_routes.capacities += attack_routes1.capacities + attack_routes2.capacities
        attack_routes.amounts_sent += attack_routes1.amounts_sent + attack_routes2.amounts_sent
        attack_routes.amounts_received += attack_routes1.amounts_received + attack_routes2.amounts_received
        attack_routes.max_htlcs += attack_routes1.max_htlcs + attack_routes2.max_htlcs
        attack_routes.betweenness += attack_routes1.betweenness + attack_routes2.betweenness
        if not attack_routes.betweenness:
            attack_routes.sort_by_capacity()
        return attack_routes

    def add_route(self, route):
        self.edges.append(route.edges)
        self.lengths.append(route.len())
        self.lock_times.append(route.time_lock)
        self.capacities.append(route.capacity)
        amount_sent = _calc_min_payment_amount_for_route(route.policies)
        self.amounts_sent.append(amount_sent)
        self.amounts_received.append(_calc_received_amount_for_route(route.policies, amount_sent))
        self.max_htlcs.append(route.edges[0]['htlc'])
        self.betweenness.append(route.betweenness)

    def len(self):
        return len(self.lengths)

    def sort_by_capacity(self):
        sorted_tuples = sorted(zip(self.edges, self.lengths, self.lock_times,
                                   self.capacities, self.amounts_sent, self.amounts_received,
                                   self.max_htlcs, self.betweenness),
                               key=lambda pair: pair[3], reverse=True)
        self.edges, self.lengths, self.lock_times, self.capacities, self.amounts_sent, self.amounts_received, self.max_htlcs, self.betweenness = list(
            zip(*sorted_tuples))

    def sort_by_betweenness(self):
        sorted_tuples = sorted(zip(self.edges, self.lengths, self.lock_times,
                                   self.capacities, self.amounts_sent, self.amounts_received,
                                   self.max_htlcs, self.betweenness),
                               key=lambda pair: pair[7], reverse=True)
        self.edges, self.lengths, self.lock_times, self.capacities, self.amounts_sent, self.amounts_received, self.max_htlcs, self.betweenness = list(
            zip(*sorted_tuples))

    def reduced(self, num_of_routes):
        """
        Returns num_of_routes first routes
        """
        attacker_results = copy.deepcopy(self)
        attacker_results.edges = attacker_results.edges[:num_of_routes]
        attacker_results.lengths = attacker_results.lengths[:num_of_routes]
        attacker_results.lock_times = attacker_results.lock_times[:num_of_routes]
        attacker_results.capacities = attacker_results.capacities[:num_of_routes]
        attacker_results.amounts_sent = attacker_results.amounts_sent[:num_of_routes]
        attacker_results.amounts_received = attacker_results.amounts_received[:num_of_routes]
        attacker_results.max_htlcs = attacker_results.max_htlcs[:num_of_routes]
        attacker_results.betweenness = attacker_results.betweenness[:num_of_routes]
        return attacker_results

    def get_capacity_needed_to_attack(self):
        """
        Returns a list of the sums of two channels capacities the attacker needs to have (in BTC) in order to attack
        each route.
        """
        return [max(MIN_CHANNEL_CAPACITY_BTC, ((a * b / 1e3) / 1e8)) +
                max(MIN_CHANNEL_CAPACITY_BTC, ((c * b / 1e3) / 1e8)) for a, b, c in
                zip(self.amounts_sent, self.max_htlcs, self.amounts_received)]


def _hop_amount_calculation(amount, min_htlc, fee_base, fee_proportional_millionths):
    """
    Given policy details of a node (fees and min_htlc) and a lower bound for the payment amount to it, returns the
    amount (in msat) that should be forwarded to it (after adding the fees).
    """
    if amount < min_htlc:  # min_htlc is the minimum amount that the node will accept
        amount = min_htlc
    return amount + fee_base + amount * fee_proportional_millionths / 1e6  # BOLT07


def _calc_min_payment_amount_for_route(nodes_policies):
    """
    Given the intermediate nodes policies along a route, returns the minimal amount (in msat) that can be transferred
    via a single payment through this route.
    """
    amount = 0
    for node in reversed(nodes_policies):
        amount = _hop_amount_calculation(amount, node['min_htlc'], node['fee_base_msat'], node['fee_rate_milli_msat'])
    if amount == 0:  # send at least 1 msat, even if all nodes along the route accept 0 (min_htlc=0 and fee_base=0)
        amount = 1
    return amount


def _hop_amount_calculation_reverse(amount, min_htlc, fee_base, fee_proportional_millionths):
    """
   Given policy details of a node (fees and min_htlc) and a payment amount sent to it for forwarding, returns the
   amount (in msat) that should be forwarded from it (after removing its' fees).
   """
    if amount + EPSILON < min_htlc:
        raise Exception('Cannot transfer less than min htlc msat')
    return (amount - fee_base) / (1 + (fee_proportional_millionths / 1e6))


def _calc_received_amount_for_route(nodes_policies, amount_sent):
    """
    Given the intermediate nodes policies along a route and a payment amount, returns the amount (in msat) that the
    recipient receives at the end of the route.
    """
    amount = amount_sent
    for node in nodes_policies:
        amount = _hop_amount_calculation_reverse(amount, node['min_htlc'], node['fee_base_msat'],
                                                     node['fee_rate_milli_msat'])
    return amount


def _append_next_edge_to_route(G, route, lock_period, max_route_length, type='capacity'):
    """
    A recursive function which adds edges to the route until the time lock lower bound or maximum route length
    is reached.
    """

    neighbours = G.adj[route.last_node]._atlas

    # tuples of all adjacent channels (adj_node_id, channel_id, capacity, cltv_delta, next_node default cltv_delta, betweenness)
    adj_channels = [(adj_node_id, channel_id, neighbours[adj_node_id][channel_id]['capacity'],
                     get_policy(neighbours[adj_node_id][channel_id], route.last_node)['time_lock_delta'],
                     CLTV_DELTA_DEFAULTS[G.nodes()[adj_node_id]['implementation']],
                     neighbours[adj_node_id][channel_id]['betweenness']) for
                    adj_node_id in neighbours for channel_id in neighbours[adj_node_id]]

    # remove edges that already appear in route
    adj_channels = [channel_tup for channel_tup in adj_channels if
                    channel_tup[1] not in list(map(lambda x: x['channel_id'], route.edges))]

    # filter to channels that keep the route locked for at least lock_period blocks.
    adj_channels = list(filter(lambda x: route.time_lock - x[3] - x[4] >= lock_period, adj_channels))

    # Dead end - if there are no potential channels to continue the route.
    if not adj_channels:
        # End the route. Reduce the cltv delta of the last node (one before the attacker), assuming it will use the
        # default according to the implementation it runs.
        route.time_lock -= CLTV_DELTA_DEFAULTS[G.nodes()[route.last_node]['implementation']]
        return route

    if type == 'capacity':
        # Extract the channels with the maximum capacity
        optimal_adj_channels = [channel_tup for channel_tup in adj_channels
                                     if channel_tup[2] == max(adj_channels, key=operator.itemgetter(2))[2]]

        # From the max capacity adjacent channels pick a channel with minimum cltv delta
        channel_tup = min(optimal_adj_channels, key=operator.itemgetter(3))
    elif type == 'betweenness':
        # Extract the channels with the maximum betweenness
        optimal_adj_channels = [channel_tup for channel_tup in adj_channels
                                     if channel_tup[5] == max(adj_channels, key=operator.itemgetter(5))[5]]

        # From the max betweenness adjacent channels pick a channel with minimum cltv delta
        channel_tup = min(optimal_adj_channels, key=operator.itemgetter(3))

    channel = neighbours[channel_tup[0]][channel_tup[1]]

    route.edges.append(channel)
    route.time_lock = route.time_lock - channel_tup[3]
    route.capacity = route.capacity + channel_tup[2]
    route.policies.append(get_policy(channel, route.last_node))
    route.last_node = channel_tup[0]

    if route.len() < max_route_length:
        return _append_next_edge_to_route(G, route, lock_period, max_route_length, type)
    route.time_lock -= CLTV_DELTA_DEFAULTS[G.nodes()[route.last_node]['implementation']]
    return route


def _locate_route(G, starting_edge, lock_period, max_route_length, type='capacity'):
    """
    Locates a route starting with the input edge, by greedily appending edges with high capacity that keep the route
    locktime >= lock_period
    """

    route_edges = list()
    route_edges.append(starting_edge)

    node1_time_lock_delta = starting_edge['node1_policy']['time_lock_delta']
    node2_time_lock_delta = starting_edge['node2_policy']['time_lock_delta']

    # We pick to route through the starting_edge in the direction which requires smaller cltv_expiry_delta
    # for forwarding payments
    edge_cltvd = node1_time_lock_delta
    first_node = starting_edge['node1_pub']
    next_node = starting_edge['node2_pub']
    if node1_time_lock_delta > node2_time_lock_delta:
        edge_cltvd = node2_time_lock_delta
        first_node = starting_edge['node2_pub']
        next_node = starting_edge['node1_pub']

    # The first channel in the route (belonging to the attacker) is not added to locktime calculation (BOLT). We reduce
    # the final cltv delta (for the last node - the attacker), and for each edge added to the route we reduce the
    # corresponding cltv delta.
    route_time_lock = LOCKTIME_MAX - MIN_FINAL_CLTV_EXPIRY - edge_cltvd
    route_capacity = starting_edge['capacity']
    route = Route(first_node, next_node, route_edges, route_time_lock, route_capacity, starting_edge['betweenness'])
    route.policies.append(get_policy(starting_edge, first_node))
    return _append_next_edge_to_route(G, route, lock_period, max_route_length, type)


def _choose_routes_by_betweenness(G, lock_period, max_route_length=MAX_ROUTE_LEN):
    """
    Splits G into disjoint routes that can be locked for at-least lock_period blocks.
    """

    G_lnd = get_LND_subgraph(G)  # Reduce graph to LND nodes
    G_lnd_complementary = get_LND_complementary_subgraph(G)  # complementary subgraph of G_lnd
    attack_routes = AttackRoutes()

    # Channels to attack, sorted by betweenness in decreasing order. Initialized to all of the network channels.
    channels_to_attack = sorted(list(map(lambda x: x[2], G.edges(data=True))), key=lambda x: x['betweenness'],
                                reverse=True)
    G_tmp = G_lnd
    while channels_to_attack:
        channel = channels_to_attack[0]
        if G_lnd.has_edge(channel['node1_pub'], channel['node2_pub'], channel['channel_id']):
            G_tmp = G_lnd
        elif G_lnd_complementary.has_edge(channel['node1_pub'], channel['node2_pub'], channel['channel_id']):
            G_tmp = G_lnd_complementary

        # Locates a route to attack that starts with a channel having the highest capacity, using a greedy algorithm.
        route = _locate_route(G_tmp, channel, lock_period, max_route_length, 'betweenness')

        # remove chosen route channels from the 'channels to attack' list and from the graph
        for edge in list({edge['channel_id']: edge for edge in route.edges}.values()):
            G.remove_edge(edge['node1_pub'], edge['node2_pub'], key=edge['channel_id'])
            G_tmp.remove_edge(edge['node1_pub'], edge['node2_pub'], key=edge['channel_id'])
        update_edges_betweenness(G)
        channels_to_attack = sorted(list(map(lambda x: x[2], G.edges(data=True))), key=lambda x: x['betweenness'],
                                reverse=True)

        attack_routes.add_route(route)

        if logger.level == logging.DEBUG:
            if not attack_routes.len() % 100:
                attack_cumulative_capacity = round(sum(list(map(lambda x: x / G.graph['network_capacity'],
                                                       attack_routes.capacities))) * 100, 1)
                logger.debug("Attacker locked " + str(attack_cumulative_capacity) + "% of the network capacity, using "
                            + str((attack_routes.len())*2) + " channels.")
                # update_edges_betweenness(G)

    return attack_routes


def _choose_routes(G, lock_period, max_route_length=MAX_ROUTE_LEN):
    """
    Splits G into disjoint routes that can be locked for at-least lock_period blocks.
    """

    attack_routes = AttackRoutes()

    # Channels to attack, sorted by capacity in decreasing order. Initialized to all of the network channels.
    channels_to_attack = sorted(list(map(lambda x: x[2], G.edges(data=True))), key=lambda x: x['capacity'],
                                reverse=True)

    while channels_to_attack:
        # Locates a route to attack that starts with a channel having the highest capacity, using a greedy algorithm.
        route = _locate_route(G, channels_to_attack[0], lock_period, max_route_length)

        # remove chosen route channels from the 'channels to attack' list and from the graph
        channels_to_attack = [channel for channel in channels_to_attack if channel not in route.edges]
        for edge in list({edge['channel_id']: edge for edge in route.edges}.values()):
            G.remove_edge(edge['node1_pub'], edge['node2_pub'], key=edge['channel_id'])

        attack_routes.add_route(route)

        if logger.level == logging.DEBUG:
            if not attack_routes.len() % 100:
                attack_cumulative_capacity = round(sum(list(map(lambda x: x / G.graph['network_capacity'],
                                                       attack_routes.capacities))) * 100, 1)
                logger.debug("Attacker locked " + str(attack_cumulative_capacity) + "% of the network capacity, using "
                            + str((attack_routes.len())*2) + " channels.")

    # sort chosen routes by capacity in descending order
    attack_routes.sort_by_capacity()
    return attack_routes


def _plot_attack_routes_data(attack_routes, network_capacity, lock_period):
    """
    Plots histograms of routes lengths and locktimes, and a graph representing the fraction of network attacked
    capacity.
    """
    logger.info("Presenting attack results, using a max rought length of " + str(MAX_ROUTE_LEN) + " hops" +
                " and a lower bound on channels locktime of " + str(lock_period) + " blocks (" +
                 str(lock_period/144) + " days)")
    #### Plot: Histogram of routes lengths (including attacker's edges)###
    fig, (ax1, ax2) = plt.subplots(2, figsize=(8, 6))
    ax1.hist(attack_routes.lengths, bins=np.arange(3, MAX_ROUTE_LEN + 2, 1), align='left', rwidth=0.8)
    ax1.set_xticks(np.arange(min(attack_routes.lengths), MAX_ROUTE_LEN + 1))
    ax1.set_xticklabels(labels=np.arange(min(attack_routes.lengths), MAX_ROUTE_LEN + 1), fontsize=14)
    ax1.set_yticks(np.arange(0, 700, 200))
    ax1.set_yticklabels(labels=np.arange(0, 700, 200), fontsize=14)
    ax1.set_xlabel('Route length', fontsize=18)
    ax1.set_ylabel('Number of occurrences', fontsize=18)

    #### Plot: Histogram of routes locktimes ###
    ax2.hist(attack_routes.lock_times, bins=MAX_ROUTE_LEN)
    ax2.set_xlim((350, 2060))
    ax2.set_ylim((0, 250))
    ax2.set_xticklabels(labels=np.arange(200, 2200, 200), fontsize=14)
    ax2.set_yticklabels(labels=np.arange(0, 300, 50), fontsize=14)
    ax2.set_yticks(np.arange(0, 250, 50))
    ax2.set_xlabel('Route locktime (blocks)', fontsize=18)
    ax2.set_ylabel('Number of occurrences', fontsize=18)
    plt.tight_layout()
    plt.savefig("plots/attack_on_network_histograms.svg")

    cumulative_attacked_capacity = np.cumsum(list(map(lambda x: x / network_capacity,
                                                      attack_routes.capacities)))  # Fraction

    fraction_of_attacked_capacity = [0.2, 0.4, 0.7, 0.9]
    attacker_channels_required = [(np.argmax(cumulative_attacked_capacity >= f) + 1) * 2
                                  for f in fraction_of_attacked_capacity]

    plt.subplots(figsize=(5, 4), dpi=200)
    #### Plot: Fraction of network attacked capacity ###
    plt.plot(np.arange(2, 2 * (len(cumulative_attacked_capacity) + 1), 2), cumulative_attacked_capacity)
    plt.yticks(np.arange(0, 1.1, 0.1))
    for i in range(len(fraction_of_attacked_capacity)):
        plt.plot(attacker_channels_required[i], fraction_of_attacked_capacity[i], 'bo', markersize=3)
        plt.text(attacker_channels_required[i] + 20 + 10*i, fraction_of_attacked_capacity[i] - 0.006*i,
                 attacker_channels_required[i], fontsize=9)
    plt.xlabel('Number of attacker channels', fontsize=12)
    plt.ylabel('Fraction of attacked capacity', fontsize=12)
    plt.savefig("plots/attack_on_network_success_rate.svg")


def _plot_costs(attack_routes):
    # Plots evaluation of the costs
    locked_liquidity = np.asarray(attack_routes.get_capacity_needed_to_attack())
    blockchain_fees = np.asarray([OPEN_CHANNEL_COST_BTC * 2]*len(locked_liquidity))
    sorted_data = np.asarray(sorted(
        [[locked_liquidity[i], blockchain_fees[i], locked_liquidity[i] + blockchain_fees[i], attack_routes.capacities[i]]
         for i in range(attack_routes.len())], key=lambda x: x[3] / x[2], reverse=True))
    x = np.cumsum(list(map(lambda x: x / 1e8, sorted_data[:, 3])))  # 1 BTC = 1e8 SAT
    y = [np.cumsum(sorted_data[:, 1]), np.cumsum(sorted_data[:, 0])]
    logger.info("The attacker can paralyze " + str(round(x[np.argmax(y[0]+y[1] > 0.25) - 1], 1)) +
                " BTC of liquidity in the Lightning Network for 3 days using less than 0.25 BTC")
    plt.figure(figsize=(5.4, 4.05), dpi=200)
    plt.stackplot(x, y, labels=['blockchain fees', 'locked liquidity'])
    plt.legend(loc='upper left')
    plt.xlabel('Network capacity locked by attack (BTC)')
    plt.ylabel('BTC')
    plt.xlim((-10, 733))
    plt.ylim((-0.008, 0.4))
    plt.savefig("plots/attack_on_network_costs.svg")


def _compute_network_attack_routes(G, lock_period, type='capacity', max_route_length=MAX_ROUTE_LEN):
    """
    Splits G into disjoint routes that can be locked for at least lock_period blocks.
    """
    logger.info("Choosing routes from LND subgraph:")
    if type == 'capacity':
        G_lnd = get_LND_subgraph(G)  # Reduce graph to LND nodes
        attack_routes_lnd = _choose_routes(G_lnd, lock_period, max_route_length)
        logger.info("Choosing routes from LND complementary subgraph:")
        G_lnd_complementary = get_LND_complementary_subgraph(G)  # complementary subgraph of G_lnd
        attack_routes_lnd_complementary = _choose_routes(G_lnd_complementary, lock_period, max_route_length)
        logger.info(
            "Combining both subgraphs results into disjoint routes in the network that can be locked for at-least "
            + str(lock_period) + " blocks (" + str(lock_period / 144) + " days)")
        attack_routes = AttackRoutes.combine(attack_routes_lnd, attack_routes_lnd_complementary)
    elif type == 'betweenness':
        G_copy = copy.deepcopy(G)
        attack_routes = _choose_routes_by_betweenness(G_copy, lock_period, max_route_length)
    return attack_routes


def attack_on_network(snapshot_path):
    """
    Analyzes the attack on the given snapshot, for a lock period of 3 days and the standard upper bound on route length
    which is 20 hops. Plots results.
    """
    logger.info("Running attack on the Lightning Network on a snapshot from " +
                datetime.datetime.strptime(snapshot_path.split("/")[1][3:13], '%Y.%m.%d').strftime("%d %B, %Y"))

    # Read json file created by LND describegraph command on the mainnet.
    json_data = load_json(snapshot_path)

    # Parse data into a networkx MultiGraph obj.
    G = load_graph(json_data)

    lock_period = 432  # 3 days

    # Attacker disconnects as many pairs of nodes as it can
    attack_routes = _compute_network_attack_routes(G, lock_period, 'betweenness')

    _plot_connectivity(G, attack_routes)

    # Attacker attempts to block as many high liquidity channels as possible
    attack_routes = _compute_network_attack_routes(G, lock_period)

    # Plot attack results (routes lengths, locktimes, capacities) for G (the given snapshot)
    _plot_attack_routes_data(attack_routes.reduced(1500), G.graph['network_capacity'], lock_period)

    # Plot attack costs for G (the given snapshot)
    _plot_costs(attack_routes)


def attack_for_different_lock_periods(snapshot_path):
    """
    Analyzes the attack on the given snapshot, for different lock periods. Plots results.
    """
    logger.info("Running the attack for different lock periods on a snapshot from " +
                datetime.datetime.strptime(snapshot_path.split("/")[1][3:13], '%Y.%m.%d').strftime("%d %B, %Y"))

    # Read json file created by LND describegraph command on the mainnet.
    json_data = load_json(snapshot_path)

    lock_periods = [days * 144 for days in np.arange(1, 7)]  # num of blocks that correspond to 1-6 days
    fig, ax = plt.subplots(figsize=(6, 5), dpi=200)
    cumulative_attacked_capacity_per_lock_period = list()  # cumulative attacked capacity for each lock period
    for lock_period in lock_periods:
        logger.info("Proccesing attack results for lock time period of " + str(lock_period) + " blocks (" +
                     str(lock_period / 144) + " days)")
        # Parse data into a networkx MultiGraph obj.
        G = load_graph(json_data)
        attack_routes = _compute_network_attack_routes(G, lock_period).reduced(800)
        cumulative_attacked_capacity = np.cumsum(list(map(lambda x: x / G.graph['network_capacity'],
                                                          attack_routes.capacities)))
        cumulative_attacked_capacity_per_lock_period.append(cumulative_attacked_capacity)
        ax.plot(np.arange(2, 2 * (len(cumulative_attacked_capacity) + 1), 2), cumulative_attacked_capacity)
    plt.legend(range(1, len(lock_periods) + 1), loc='lower right', title="Lock Period (days)")
    plt.xlabel('Number of attacker channels', fontsize=14)
    plt.xlim((-40, 1500))
    plt.ylim((-0.04, 1.04))
    plt.ylabel('Fraction of attacked capacity', fontsize=14)
    axins = zoomed_inset_axes(ax, 20, loc=2)
    for cumulative_attacked_capacity in cumulative_attacked_capacity_per_lock_period:
        axins.plot(np.arange(2, 2 * (len(cumulative_attacked_capacity) + 1), 2), cumulative_attacked_capacity)
    x1, x2, y1, y2 = 1100, 1119, 0.914, 0.928
    axins.set_xlim(x1, x2)
    axins.set_ylim(y1, y2)
    plt.yticks(visible=False)
    plt.xticks(visible=False)
    plt.grid(b=None)
    from mpl_toolkits.axes_grid1.inset_locator import mark_inset
    mark_inset(ax, axins, loc1=2, loc2=4, fc="none", ec="0.5")
    plt.savefig("plots/attack_on_network_by_lock_period.svg", bbox_inches='tight')


def attack_for_different_max_route_lengths(snapshot_path):
    """
    Analyzes the attack on the given snapshot, for different upper bounds on route length. Plots results.
    """
    logger.info("Running the attack for different upper bounds on route length on a snapshot from " +
                datetime.datetime.strptime(snapshot_path.split("/")[1][3:13], '%Y.%m.%d').strftime("%d %B, %Y"))

    # Read json file created by LND describegraph command on the mainnet.
    json_data = load_json(snapshot_path)
    lock_period = 432  # 3 days

    max_route_lengths = [20, 14, 10, 8, 6]
    plt.figure(figsize=(6, 5), dpi=200)
    for max_route_len in max_route_lengths:
        logger.info("Proccesing attack results for max route length of " + str(max_route_len) + " hops")
        # Parse data into a networkx MultiGraph obj.
        G = load_graph(json_data)
        attack_routes = _compute_network_attack_routes(G, lock_period, max_route_len)
        cumulative_attacked_capacity = np.cumsum(list(map(lambda x: x / G.graph['network_capacity'],
                                                          attack_routes.capacities)))
        plt.plot(np.arange(2, 2 * (len(cumulative_attacked_capacity) + 1), 2), cumulative_attacked_capacity)
    plt.legend(max_route_lengths,
               loc='lower right', title="Maximum Route Length")
    plt.xlim((-50, 3130))
    plt.ylim((-0.02, 1.02))
    plt.xlabel('Number of attacker channels', fontsize=14)
    plt.ylabel('Fraction of attacked capacity', fontsize=14)
    plt.savefig("plots/attack_on_network_by_max_route_len.svg", bbox_inches='tight')


def attack_for_different_snapshots(snapshots_dir):
    """
    Plots the attack results on different snapshots.
    """
    snapshots_list = [f for f in listdir(snapshots_dir) if isfile(join(snapshots_dir, f)) and f.endswith('json')]
    lock_period = 432  # 3 days
    fig, ax = plt.subplots()
    attacked_capacity_by_snapshot = list()

    for G_str in snapshots_list:
        logger.info("Processing attack results for a snapshot taken on " +
                    datetime.datetime.strptime(G_str[3:13], '%Y.%m.%d').strftime("%d %B, %Y"))
        json_data = load_json(snapshots_dir + G_str)
        G = load_graph(json_data)
        attack_routes = _compute_network_attack_routes(G, lock_period)
        cumulative_attacked_capacity = [0] + np.cumsum(list(map(lambda x: x / G.graph['network_capacity'],
                                                          attack_routes.capacities)))[:800]

        x = np.arange(0, 2 * len(cumulative_attacked_capacity), 2)
        y = cumulative_attacked_capacity
        attacked_capacity_by_snapshot.append(y)
        ax.plot(x, y)

    plt.legend([datetime.datetime.strptime(G_str[3:13], '%Y.%m.%d').strftime("%d %B %Y") for G_str in snapshots_list],
               loc='lower right', fontsize=11)
    plt.xlabel('Number of attacker channels', fontsize=13)
    plt.ylabel('Fraction of attacked capacity', fontsize=13)
    plt.xlim((-40, 1500))
    plt.ylim((-0.04, 1.04))
    axins = zoomed_inset_axes(ax, 12, loc=2)
    for y in attacked_capacity_by_snapshot:
        axins.plot(x, y)
    x1, x2, y1, y2 = 1150, 1177, 0.91, 0.9363
    axins.set_xlim(x1, x2)
    axins.set_ylim(y1, y2)
    plt.yticks(visible=False)
    plt.xticks(visible=False)
    plt.grid(b=None)
    mark_inset(ax, axins, loc1=2, loc2=4, fc="none", ec="0.5")
    plt.savefig("plots/attack_on_network_different_snapshots.svg", bbox_inches='tight')


def get_all_pairs_of_nodes(G):
    nodes = list(G.nodes())
    result = []
    for p1 in range(len(nodes)):
        for p2 in range(p1 + 1, len(nodes)):
            result.append([nodes[p1], nodes[p2]])
    return result


def get_connected_pairs(G, pairs):
    p = list()
    for pair in pairs:
        if nx.has_path(G, source=pair[0], target=pair[1]):
            p.append(pair)
    return p


def _plot_connectivity(G, attack_routes):
    """
    Plots the fraction of connected pairs of nodes in the network, showing how the attack affects connectivity between
     nodes in the network, when we remove channels with high betweenness value first.
    """
    logger.info("Presenting fraction of nodes kept connected")
    pairs = get_all_pairs_of_nodes(G)
    total_pairs = len(pairs)
    logger.debug("Total pairs of nodes in the network: " + str(total_pairs))
    connected_pairs = get_connected_pairs(G, pairs)
    logger.debug("Total initial connected (by path) pairs of nodes in the network: " + str(len(connected_pairs)))
    initial_connected_pairs_count = len(connected_pairs)
    num_of_channels = list()
    num_of_channels.append(0)
    connected_pairs_count_list = list()
    connected_pairs_count_list.append(initial_connected_pairs_count)
    i = 0
    for edges in attack_routes.edges:
        for edge in list({edge['channel_id']: edge for edge in edges}.values()):
            G.remove_edge(edge['node1_pub'], edge['node2_pub'], key=edge['channel_id'])
        if i % 5 == 0:
            connected_pairs = get_connected_pairs(G, connected_pairs)
            connected_pairs_count_list.append(len(connected_pairs))
            num_of_channels.append((i+1)*2)
            logger.debug(str(connected_pairs_count_list[-1]/total_pairs) + "\t" + str(connected_pairs_count_list[-1]/initial_connected_pairs_count))
        i += 1

    plt.subplots(figsize=(5, 4), dpi=200)
    #### Plot: Fraction of network attacked capacity ###
    plt.plot(num_of_channels, [i/total_pairs for i in connected_pairs_count_list])
    plt.yticks(np.arange(0, 1.1, 0.1))
    plt.xlabel('Number of attacker channels', fontsize=12)
    plt.ylabel('Fraction of connected pairs', fontsize=12)
    plt.savefig("plots/attack_on_network_connectivity.svg")
    plt.subplots(figsize=(5, 4), dpi=200)


def main():

    coloredlogs.install(fmt='%(asctime)s [%(module)s: line %(lineno)d] %(levelname)s %(message)s',
                        level=logging.DEBUG, logger=logger)

    snapshot_path = 'snapshots/LN_2020.05.21-08.00.01.json'

    attack_on_network(snapshot_path)

    attack_for_different_lock_periods(snapshot_path)

    attack_for_different_max_route_lengths(snapshot_path)

    snapshots_dir = 'snapshots/test/'
    attack_for_different_snapshots(snapshots_dir)

if __name__ == "__main__":
    main()