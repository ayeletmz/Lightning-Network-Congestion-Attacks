from network_parser import *
import matplotlib.pyplot as plt
from os import listdir
from os.path import isfile, join
import networkx as nx
from collections import Counter, deque
import datetime
import numpy as np
import time

"""
    This module evaluates the current state of the Lightning Network given a snapshot (generated by using LND's
    describegraph command). We plot some statistics on the parameters announced by nodes in channels on the Lightning
    Network and perform classification using Lightning implementation defaults in order to infer the
    implementation of each node.
"""


def _get_policy_field(edge, field):
    # Returns the input parameter (field) values as declared in the policies of the input channel (edge).
    return [int(edge['node1_policy'][field]), int(edge['node2_policy'][field])]


def _get_edge_time_lock_delta(edge):
    return _get_policy_field(edge, 'time_lock_delta')


def _get_min_htlc(edge):
    return _get_policy_field(edge, 'min_htlc')


def _get_fee_base_msat(edge):
    return _get_policy_field(edge, 'fee_base_msat')


def _get_fee_proportional_millionths(edge):
    return _get_policy_field(edge, 'fee_rate_milli_msat')


def _channel_exceeds_upper_bound(edge_deltas, upper_bound):
    # Checks whether the channel has a peer with configured cltv_delta greater or equal that the given upper_bound.
    if max(edge_deltas) >= upper_bound:
        return True
    return False


def _channel_exceeds_lower_bound(edge_deltas, lower_bound):
    # Checks whether the channel has a peer with configured cltv_delta smaller or equal that the given lower_bound.
    if min(edge_deltas) <= lower_bound:
        return True
    return False


def _get_peer_cltv_delta(channel, node):
    # Returns cltv_delta of the node in the channel.
    if node == channel['node1_pub']:
        return channel['node1_policy']['time_lock_delta']
    elif node == channel['node2_pub']:
        return channel['node2_policy']['time_lock_delta']
    else:
        raise Exception('Error: Node ' + node + ' is not a peer to channel ' + channel['channel_id'])


######################## Lightning Implementation Inference ########################


def plot_implementation_distribution(G):
    # Plots a pie chart of the implementation distribution of nodes in G
    nodes_implementation = nx.get_node_attributes(G, 'implementation')
    count = Counter(nodes_implementation.values())
    logger.debug("Nodes implementation distribution: " + str(count))
    x_labels, y_labels = zip(*count.items())
    sum_ = sum(y_labels)
    y_labels = [i *100/sum_ for i in y_labels]
    y_labels = round_distribution(y_labels, 1)

    fig, ax = plt.subplots()
    # The following trick (matching labels to their percent of appeareance)
    # works only if the percent values are all different.
    assert len(set(y_labels)) == len(y_labels)
    label_by_percent = {y_labels[i]: str(x_labels[i]) for i in range(len(x_labels))}
    ax.pie(y_labels, colors=sns.color_palette("colorblind"),
           autopct=lambda pct: "{:s}".format(label_by_percent[round(pct, 1)]),
           shadow=True, startangle=0, textprops={'fontsize': 16})
    ax.pie(y_labels, autopct=lambda pct: "\n\n ({:.1f}%)".format(pct),
           shadow=True, startangle=0, textprops={'fontsize': 11})
    # Equal aspect ratio ensures that pie is drawn as a circle
    ax.axis('equal')
    plt.title("Nodes Implementation", fontsize=18)
    plt.tight_layout()
    plt.savefig("plots/impl_dist.svg")


def plot_capacity_implementation_distribution(G):
    # Plots a pie chart of the percentage of capacity in LND channels (both sides of the channels run LND)
    # vs the rest of the channels.
    capacity_impl = dict()
    capacity_impl['LND'] = sum(list(map(lambda x: x[2]['capacity'], get_LND_subgraph(G).edges(data=True))))\
                           * 100 / G.graph['network_capacity']
    capacity_impl['Complementary'] =\
        sum(list(map(lambda x: x[2]['capacity'], get_LND_complementary_subgraph(G).edges(data=True)))) * 100\
        / G.graph['network_capacity']
    capacity_impl = round_distribution(capacity_impl, 1)
    x_labels, y_labels = zip(*capacity_impl.items())

    fig, ax = plt.subplots()
    # The following trick (matching labels to their percent of appeareance)
    # works only if the percent values are all different.
    assert len(set(y_labels)) == len(y_labels)
    label_by_percent = {y_labels[i]: str(x_labels[i]) for i in range(len(x_labels))}
    ax.pie(y_labels, explode=(0, 0.1), colors=sns.color_palette("colorblind"),
           autopct=lambda pct: "{:s}".format(label_by_percent[round(pct, 1)]),
           shadow=True, startangle=0, textprops={'fontsize': 16})
    ax.pie(y_labels, explode=(0, 0.1), autopct=lambda pct: "\n\n ({:.1f}%)".format(pct),
           shadow=True, startangle=0, textprops={'fontsize': 12})
    # Equal aspect ratio ensures that pie is drawn as a circle
    ax.axis('equal')
    plt.title("LND Subgraph Capacity", fontsize=18)
    plt.tight_layout()
    plt.savefig("plots/capacity_impl_dist.svg")


def plot_implementation_distribution_for_different_snapshots(snapshots_dir):
    """
    Plots the implementation distribution of nodes for different snapshots.
    """
    snapshots_list = [f for f in listdir(snapshots_dir) if isfile(join(snapshots_dir, f)) and f.endswith('json')]
    dates = list()
    impl_dist_by_snapshot = dict()

    for G_str in snapshots_list:
        logger.debug("Processing graph " + G_str[3:13])
        dates.append(datetime.datetime.strptime(G_str[3:13], '%Y.%m.%d'))
        json_data = load_json(snapshots_dir + G_str)
        G = load_graph(json_data)
        nodes_implementation = nx.get_node_attributes(G, 'implementation')
        count = Counter(nodes_implementation.values())
        impl_labels, y_labels = zip(*count.items())
        sum_ = sum(y_labels)
        y_labels = [i * 100 / sum_ for i in y_labels]
        impl_dist_by_snapshot[G_str[3:13]] = dict(zip(impl_labels, round_distribution(y_labels)))

    x_labels = [time.mktime(date.timetuple()) for date in dates]
    date_labels = [date.strftime("%d %b %y") for date in dates]
    fig, ax = plt.subplots(figsize=(7.5, 5), dpi=200)
    for imp in impl_labels:
        y_labels = [impl_dist_by_snapshot[G_str[3:13]][imp] for G_str in snapshots_list]
        ax.plot(x_labels, y_labels, marker='o')
        for i in [0, 1, 5, 8, 12]:
            plt.text(x_labels[i], y_labels[i] + 1.5, round(y_labels[i]/100, 2), fontsize=9)

    ax.set_xticklabels([])
    for i, txt in enumerate(date_labels):
        plt.text(x_labels[i], -18.5, txt, fontsize=11, rotation=-45)
    plt.legend(impl_labels, loc='center right', title="Implementation")
    ax.set_xlim(np.array([-0.07 * (x_labels[2] - x_labels[1]), 0.75 * (x_labels[2] - x_labels[1])]) + ax.get_xlim())
    ax.set_yticklabels(np.arange(-2, 10, 2) / 10)
    plt.xlabel('Snapshots                                                        ', fontsize=15)
    plt.ylabel('Fraction of the network', fontsize=15)
    plt.savefig("plots/impl_dist_by_snapshot.svg")


def run_impl_infer_plots(snapshot_path, snapshots_dir):
    # produces plots related to the Lightning implementation inference process

    # Read json file created by LND describegraph command on the mainnet.
    json_data = load_json(snapshot_path)
    # Parse data into a networkx MultiGraph obj.
    G = load_graph(json_data)

    plot_implementation_distribution(G)
    plot_capacity_implementation_distribution(G)
    plot_implementation_distribution_for_different_snapshots(snapshots_dir)



######################## Amounts Transferred Parameters Plots ########################


def plot_htlc_min(snapshot_path):
    # Plots a pie chart presenting the distribution of htlc_minimum_msat parameter, which indicates the minimum amount
    # in millisatoshi (msat) that the node will be willing to transfer.

    json_data = load_json(snapshot_path)
    # Remove channels that are disabled or that do not declare their policies.
    json_data = filter_snapshot_data(json_data)

    min_htlc_values = sum([_get_min_htlc(e) for e in json_data['edges']], [])
    min_htlc_count = sorted(Counter(min_htlc_values).items(), key=lambda item: item[1], reverse=True)
    min_htlc_percent = list(map(lambda x: (x[0], x[1] * 100 / sum(j for i, j in min_htlc_count)), min_htlc_count))
    data_to_plot = min_htlc_percent[:3]
    data_to_plot.append(('other', sum(j for i, j in min_htlc_percent[3:])))
    x_labels = [val[0] for val in data_to_plot]
    y_labels = round_distribution([val[1] for val in data_to_plot], 1)

    max_ = max(min_htlc_values)
    logger.debug("max value of htlc_min: " + str(max_) + " msat which are " + str(max_/ 1e11) + " BTC")
    logger.info(str(round(len([i for i in min_htlc_values if i <= 1000]) / len(min_htlc_values)*100, 1)) +
                "% of the network with min htlc <= 1000")

    fig, ax = plt.subplots()
    explode = (0.02, 0.02, 0.02, 0.3)
    # The following trick (matching labels to their percent of appeareance)
    # works only if the percent values are all different.
    assert len(set(y_labels)) == len(y_labels)
    label_by_percent = {y_labels[i]: str(x_labels[i]) for i in range(len(x_labels))}
    ax.pie(y_labels, explode=explode, colors=sns.color_palette("colorblind"),
           autopct=lambda pct: "{:s}".format(label_by_percent[round(pct, 1)]), shadow=True, startangle=45,
           textprops={'fontsize': 15})
    ax.pie(y_labels, explode=explode, autopct=lambda pct: "\n\n ({:.1f}%)".format(pct),
                                        shadow=True, startangle=45, textprops={'fontsize': 11})
    ax.axis('equal')
    plt.title("htlc_minimum_msat", fontsize=18)
    plt.tight_layout()
    plt.savefig("plots/htlc_min.svg")


def plot_fee_base(snapshot_path):
    # Plots a pie chart presenting the distribution of fee_base_msat parameter, which indicates , the constant
    # fee (in msat) the node will charge per transfer.

    json_data = load_json(snapshot_path)
    # Remove channels that are disabled or that do not declare their policies.
    json_data = filter_snapshot_data(json_data)

    fee_base_values = sum([_get_fee_base_msat(e) for e in json_data['edges']], [])
    fee_base_count = sorted(Counter(fee_base_values).items(), key=lambda item: item[1], reverse=True)
    fee_base_percent = list(map(lambda x: (x[0], x[1] * 100 / sum(j for i, j in fee_base_count)), fee_base_count))
    # pick the index where the percent gets lower than 1.1%
    bound_idx = min([i for i, n in enumerate(fee_base_percent) if n[1] < 1.3])
    data_to_plot = sorted(fee_base_percent[:bound_idx], reverse=True)
    data_to_plot.append(('other', sum(j for i, j in fee_base_percent[bound_idx:])))  # (with <1.3%)
    x_labels = [val[0] for val in data_to_plot]
    y_labels = round_distribution([val[1] for val in data_to_plot], 2)
    max_ = max(fee_base_values)
    logger.debug("max value of fee_base: " + str(max_) + " msat which are " + str(max_/ 1e11) + " BTC")
    logger.info(str(round(len([i for i in fee_base_values if i <= 1000]) / len(fee_base_values) * 100,
                    1)) + "% of the network with fee base <= 1000")

    fig, ax = plt.subplots()
    # The following trick (matching labels to their percent of appeareance)
    # works only if the percent values are all different.
    assert len(set(y_labels)) == len(y_labels)
    label_by_percent = {y_labels[i]: str(x_labels[i]) for i in range(len(x_labels))}
    ax.pie(y_labels, colors=sns.color_palette("colorblind"),
                                        autopct=lambda pct: "{:s}".format(label_by_percent[round(pct, 2)]),
                                        shadow=True, startangle=0, textprops={'fontsize': 15})
    ax.pie(y_labels, autopct=lambda pct: "\n\n ({:.1f}%)".format(pct),
                                        shadow=True, startangle=0, textprops={'fontsize': 8})
    ax.axis('equal')
    plt.title("fee_base_msat", fontsize=18)
    plt.tight_layout()
    plt.savefig("plots/fee_base.svg")


def plot_fee_proportional(snapshot_path):
    # Plots a pie chart presenting the distribution of fee_proportional_millionths parameter, which indicates the
    # amount (in millionths of a satoshi) that nodes will charge per transferred satoshi.

    json_data = load_json(snapshot_path)
    # Remove channels that are disabled or that do not declare their policies.
    json_data = filter_snapshot_data(json_data)

    fee_proportional_values = sum([_get_fee_proportional_millionths(e) for e in json_data['edges']], [])
    fee_proportional_count = sorted(Counter(fee_proportional_values).items(), key=lambda item: item[1], reverse=True)
    fee_proportional_percent = list(map(lambda x: (x[0], x[1] * 100 / sum(j for i, j in fee_proportional_count)),
                                        fee_proportional_count))
    # pick the index where the percent gets lower than 2.8%
    bound_idx = min([i for i, n in enumerate(fee_proportional_percent) if n[1] < 2])
    data_to_plot = sorted(fee_proportional_percent[:bound_idx], reverse=True)
    data_to_plot.append(('other', sum(j for i, j in fee_proportional_percent[bound_idx:])))  # (with <2%)
    # The rotation of the list is made because it improves the visibility
    # of the pie chart in matching the colors to slices.
    data_to_plot = deque(data_to_plot)
    data_to_plot.rotate(3)
    x_labels = [val[0] for val in data_to_plot]
    y_labels = round_distribution([val[1] for val in data_to_plot], 2)

    max_ = max(fee_proportional_values)
    logger.debug("max value of fee_proportional_millionths: " + str(max_) + " msat which are " + str(max_/ 1e11) + " BTC")
    logger.info(str(round(len([i for i in fee_proportional_values if i <= 1]) / len(
        fee_proportional_values) * 100, 1)) + "% of the network with fee proportional millionths <= 1")
    logger.info(str(round(len([i for i in fee_proportional_values if i <= 1000]) / len(fee_proportional_values) * 100,
                    1)) + "% of the network with fee proportional millionths <= 1000")

    fig, ax = plt.subplots()
    # The following trick (matching labels to their percent of appearance)
    # works only if the percent values are all different.
    assert len(set(y_labels)) == len(y_labels)
    label_by_percent = {y_labels[i]: str(x_labels[i]) for i in range(len(x_labels))}
    ax.pie(y_labels, colors=sns.color_palette("colorblind"),
           autopct=lambda pct: "{:s}".format(label_by_percent[round(pct, 2)]),
           shadow=True, startangle=0, textprops={'fontsize': 10})
    ax.pie(y_labels, autopct=lambda pct: "\n\n ({:.1f}%)".format(pct),
           shadow=True, startangle=0, textprops={'fontsize': 6})
    ax.axis('equal')
    plt.title("fee_proportional_millionths", fontsize=18)
    plt.tight_layout()
    plt.savefig("plots/fee_proportional.svg")


def run_amounts_transferred_plots(snapshot_path):
    # produces plots related to the amounts transferred through the network (bounds and fees)

    plot_htlc_min(snapshot_path)
    plot_fee_base(snapshot_path)
    plot_fee_proportional(snapshot_path)




######################## Timelock Plots ########################


def plot_cltv_delta(snapshot_path):
    # Plots a pie chart presenting the distribution of cltv_expiry_delta parameter, which indicates the
    # minimum difference in htlc timeouts the forwarding node will accept.

    json_data = load_json(snapshot_path)
    # Remove channels that are disabled or that do not declare their policies.
    json_data = filter_snapshot_data(json_data)

    cltv_deltas_per_edge = [_get_edge_time_lock_delta(e) for e in json_data['edges']]
    percent_of_mixed_channels = round([_channel_exceeds_lower_bound(edge_deltas, 40)
                                       and _channel_exceeds_upper_bound(edge_deltas, 144) for
        edge_deltas in cltv_deltas_per_edge].count(True) / (len(cltv_deltas_per_edge)) * 100, 1)
    logger.debug(
        "percent of channels with one peer configured cltv_delta <= 40 and the other configured cltv_delta >= 144: "
        + str(percent_of_mixed_channels) + "%")

    cltv_delta_values = sum(cltv_deltas_per_edge, [])
    cltv_delta_count = sorted(Counter(cltv_delta_values).items(), key=lambda item: item[1], reverse=True)
    cltv_delta_percent = list(map(lambda x: (x[0], x[1] * 100 / sum(j for i, j in cltv_delta_count)), cltv_delta_count))
    logger.info("The cltv delta default values (" + ', '.join(map(str, CLTV_DELTA_DEFAULTS.values())) +
                ") from the different major implementations constitute " +
                str(round(sum([dict(cltv_delta_percent)[cltv_delta]
                               for cltv_delta in CLTV_DELTA_DEFAULTS.values()]), 1)) + "% of the total.")
    # pick the index where the percent gets lower than 1%
    bound_idx = min([i for i, n in enumerate(cltv_delta_percent) if n[1] < 2])
    data_to_plot = sorted(cltv_delta_percent[:bound_idx], reverse=True)
    data_to_plot.append(('other', sum(j for i, j in cltv_delta_percent[bound_idx:])))  # (with <1%)
    x_labels = [val[0] for val in data_to_plot]
    y_labels = round_distribution([val[1] for val in data_to_plot], 1)

    # https://github.com/mwaskom/seaborn/blob/master/seaborn/palettes.py
    deep = ["#8172B3", "#4C72B0", "#DD8452", "#55A868", "#C44E52", "#DA8BC3",
            "#937860", "#8C8C8C", "#CCB974", "#64B5CD"]

    fig, ax = plt.subplots()
    # The following trick (matching labels to their percent of appeareance)
    # works only if the percent values are all different.
    assert len(set(y_labels)) == len(y_labels)
    label_by_percent = {y_labels[i]: str(x_labels[i]) for i in range(len(x_labels))}
    ax.pie(y_labels, autopct=lambda pct: "{:s}".format(label_by_percent[round(pct, 1)]),
                                        shadow=True, startangle=60, textprops={'fontsize': 12})
    ax.pie(y_labels, colors=deep, autopct=lambda pct: "\n\n ({:.1f}%)".format(pct),
                                        shadow=True, startangle=60, textprops={'fontsize': 6})
    ax.axis('equal')
    plt.title("cltv_expiry_delta", fontsize=18)
    plt.tight_layout()
    plt.savefig("plots/cltv_delta.svg")


def plot_node_cltv_delta(snapshot_path):
    # Plots a pie chart presenting the timelock delta distribution by nodes (rather than by channel peers),
    # which we do by looking at the most common value of cltv_expiry_delta used by each node.

    json_data = load_json(snapshot_path)
    # Remove node_cltv_deltas that are disabled or that do not declare their policies.
    json_data = filter_snapshot_data(json_data)
    # Parse data into a networkx MultiGraph obj.
    G = load_graph(json_data)
    # nodes sorted by decreasing capacity
    nodes = sorted(G.nodes(data=True), key=lambda x: x[1]['capacity'], reverse=True)
    nodes_cltv_deltas = list()
    for node in nodes:
        neighbours = G.adj[node[0]]._atlas
        node_cltv_deltas = [_get_peer_cltv_delta(neighbours[adj_node_id][channel_id], node[0]) for adj_node_id in
                            neighbours for channel_id in neighbours[adj_node_id]]
        node_cltv_deltas_count = sorted(Counter(node_cltv_deltas).items(), key=lambda item: item[1], reverse=True)
        nodes_cltv_deltas.append(node_cltv_deltas_count[0][0])
    nodes_cltv_deltas_count = sorted(Counter(nodes_cltv_deltas).items(), key=lambda item: item[1], reverse=True)
    nodes_cltv_deltas_percent = list(map(lambda x: (x[0], x[1] * 100 / sum(j for i, j in nodes_cltv_deltas_count)),
                                         nodes_cltv_deltas_count))
    # pick the index where the percent gets lower than 1%
    bound_idx = min([i for i, n in enumerate(nodes_cltv_deltas_percent) if n[1] < 1])
    data_to_plot = nodes_cltv_deltas_percent[:bound_idx]
    data_to_plot.append(('other', sum(j for i, j in nodes_cltv_deltas_percent[bound_idx:])))  # (with <1%)
    x_labels = [val[0] for val in data_to_plot]
    y_labels = round_distribution([val[1] for val in data_to_plot], 1)

    fig, ax = plt.subplots()
    # The following trick (matching labels to their percent of appeareance)
    # works only if the percent values are all different.
    assert len(set(y_labels)) == len(y_labels)
    label_by_percent = {y_labels[i]: str(x_labels[i]) for i in range(len(x_labels))}
    ax.pie(y_labels, colors=sns.color_palette("colorblind"),
           autopct=lambda pct: "{:s}".format(label_by_percent[round(pct, 1)]), shadow=True, startangle=20,
           textprops={'fontsize': 12})
    ax.pie(y_labels, autopct=lambda pct: " "*(len(label_by_percent[round(pct, 1)])*2+17)+"({:.1f}%)".format(pct),
           shadow=True, startangle=20, textprops={'fontsize': 9})
    ax.axis('equal')
    plt.title("cltv_expiry_delta by nodes", fontsize=18)
    plt.tight_layout()
    plt.savefig("plots/node_cltv_delta.svg")


def plot_cltv_delta_for_different_snapshots(snapshots_dir):
    """
    Plots the cltv_expiry_delta distribution of nodes for different snapshots.
    """
    snapshots_list = [f for f in listdir(snapshots_dir) if isfile(join(snapshots_dir, f)) and f.endswith('json')]
    dates = list()
    cltvd_dist_by_snapshot = dict()

    for G_str in snapshots_list:
        logger.debug("Processing graph " + G_str[3:13])
        dates.append(datetime.datetime.strptime(G_str[3:13], '%Y.%m.%d'))
        json_data = load_json(snapshots_dir + G_str)
        # Remove nodes that are disabled or that do not declare their policies.
        json_data = filter_snapshot_data(json_data)
        cltv_delta_values = sum([_get_edge_time_lock_delta(e) for e in json_data['edges']], [])
        cltv_delta_count = sorted(Counter(cltv_delta_values).items(), key=lambda item: item[1], reverse=True)
        cltv_delta_percent = list(map(lambda x: (x[0], x[1] * 100 / sum(j for i, j in cltv_delta_count)),
                                      cltv_delta_count))
        cltvd_dist_by_snapshot[G_str[3:13]] = cltv_delta_percent

    x_labels = [time.mktime(date.timetuple()) for date in dates]
    date_labels = [date.strftime("%d %b %y") for date in dates]

    # We consider the 3 top rated cltv_delta_labels from each snapshot
    cltv_delta_labels = list(set([cltvd_dist_by_snapshot[snapshot][i][0] for snapshot in cltvd_dist_by_snapshot.keys()
                                  for i in range(3)]))
    cltv_delta_labels.sort()
    cltv_delta_labels.append('other')
    fig, ax = plt.subplots(figsize=(7.5, 5), dpi=200)
    i = 0
    markers = ['d', '>', 's', 'H', 'o', '*']
    for cltv_delta in cltv_delta_labels:
        cltv_delta_by_snapshot = list()
        for G_str in snapshots_list:
            G_str_dict = dict(cltvd_dist_by_snapshot[G_str[3:13]])
            if cltv_delta == 'other':
                cltv_delta_by_snapshot.append(
                    (G_str[3:13], round(sum(value for key, value in G_str_dict.items()
                                            if key not in cltv_delta_labels), 1)))
            else:
                if cltv_delta in G_str_dict:
                    cltv_delta_by_snapshot.append((G_str[3:13], round(G_str_dict[cltv_delta], 1)))
                else:
                    cltv_delta_by_snapshot.append((G_str[3:13], 0))
        y_labels = [val[1] for val in cltv_delta_by_snapshot]
        ax.plot(x_labels, y_labels, marker=markers[i], label=cltv_delta)
        i += 1

    ax.set_xticklabels([])
    for i, txt in enumerate(date_labels):
        plt.text(x_labels[i], -16, txt, fontsize=11, rotation=-45)
    handles, labels = ax.get_legend_handles_labels()
    plt.legend(handles, labels, loc='upper center', title="Timelock (in blocks)", prop={'size': 9.5})
    ax.set_xlim(np.array([-0.07 * (x_labels[2] - x_labels[1]), 0.7 * (x_labels[2] - x_labels[1])]) + ax.get_xlim())
    ax.set_yticklabels(np.arange(-1, 9) / 10)
    plt.xlabel('Snapshots                                                        ', fontsize=15)
    plt.ylabel('Fraction of the network', fontsize=15)
    plt.savefig("plots/cltv_delta_by_snapshot.svg")


def run_timelock_plots(snapshot_path, snapshots_dir):
    # produces plots related to the timelocks configured by peers in the network.

    plot_cltv_delta(snapshot_path)
    plot_node_cltv_delta(snapshot_path)
    plot_cltv_delta_for_different_snapshots(snapshots_dir)

################################################################


def round_distribution(dist, ndigits=0):
    """
    Given a distribution (list or dict) that sums to 100 (percent), it rounds the values to a ndigits precision
    in decimal digits.
    It fixes the sum to remain 100 in case needed, by changing the value that was most affected by rounding.
    """
    if type(dist) is list:
        assert all(val >= 0 for val in dist) and round(sum(dist), ndigits) == 100
        round_dist = [round(i, ndigits) for i in dist]
        if round(sum(round_dist), ndigits) != 100:
            idx = np.argmax([abs(a_i - b_i) for a_i, b_i in zip(round_dist, dist)])
            round_dist[idx] = round(round_dist[idx] - (sum(round_dist) - 100), ndigits)
    if type(dist) is dict:
        assert all(val >= 0 for val in dist.values()) and round(sum(dist.values()), ndigits) == 100
        round_dist = {k: round(v, ndigits) for k, v in dist.items()}
        if round(sum(round_dist.values()), ndigits) != 100:
            key = max({abs(dist(k) - round_dist(k)): k for k in dist.keys()})[1]
            round_dist[key] = round(round_dist[idx] - (sum(round_dist.values()) - 100), ndigits)
    return round_dist


def main():

    coloredlogs.install(fmt='%(asctime)s [%(module)s: line %(lineno)d] %(levelname)s %(message)s',
                        level=logging.DEBUG, logger=logger)
    snapshot_path = 'snapshots/LN_2020.09.21-08.00.01.json'
    snapshots_dir = 'snapshots/test/'

    run_impl_infer_plots(snapshot_path, snapshots_dir)
    run_amounts_transferred_plots(snapshot_path)
    run_timelock_plots(snapshot_path, snapshots_dir)


if __name__ == "__main__":
    main()
