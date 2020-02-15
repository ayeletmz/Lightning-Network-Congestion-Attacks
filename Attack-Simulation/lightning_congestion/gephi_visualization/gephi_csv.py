from network_parser import *
import csv
from pathlib import Path

# Path to projects' root directory
ROOT_DIR = str(Path(__file__).parent.parent)


def generate_csv_files(file_path):
    """
    Generates csv files (for nodes and edges) to be imported to Gephi in order to visualize the network snapshot.
    """

    file_name = file_path.split("/")[-1]
    # Read json file created by LND describegraph command on the mainnet.
    json_data = load_json(file_path)
    # Parse data into a networkx MultiGraph obj.
    G = load_graph(json_data)

    with open('LN_nodes_'+file_name[3:13]+'_.csv', 'a+', newline='', encoding='utf8', errors='ignore') as file_object:
        csv_file = csv.writer(file_object)
        nodes = list(G.nodes(data=True))
        csv_file.writerow(['id', 'label', 'weight'] + list(reversed(list(nodes[0][1].keys()))))
        for node in nodes:
            csv_file.writerow([node[0], node[1]['alias'], node[1]['capacity']/1e8] + list(reversed(list(node[1].values()))))

    file_object.close()

    with open('LN_edges_'+file_name[3:13]+'_.csv', 'a+', newline='', encoding='utf8', errors='ignore') as file_object:
        csv_file = csv.writer(file_object)
        edges = list(G.edges(data=True))
        keys = ['id', 'label', 'source', 'target', 'weight', 'capacity', 'max_htlc'] + \
               list(edges[0][2]['node1_policy'].keys())
        csv_file.writerow(keys)
        for edge in edges:
            edge_data = list(edge[2].values())
            direction1_values = [edge[2]['channel_id']+"_1", edge[2]['channel_id']+"_1"] +\
                                edge_data[3:5] + [edge_data[5]/1e8 , edge_data[5], edge_data[10]] + \
                                list(edge[2]['node1_policy'].values())
            direction2_values = [edge[2]['channel_id']+"_2", edge[2]['channel_id']+"_2"] + [edge_data[4], \
                                edge_data[3], edge_data[5]/1e8, edge_data[5], edge_data[10]] + list(edge[2]['node2_policy'].values())
            csv_file.writerow(direction1_values)
            csv_file.writerow(direction2_values)

    file_object.close()


def main():
    file_path = ROOT_DIR + '/snapshots/LN_2020.01.01-08.00.01.json'
    generate_csv_files(file_path)


if __name__ == "__main__":
    main()