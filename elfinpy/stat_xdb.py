#!/usr/bin/env python3

import argparse, sys

import warnings
warnings.filterwarnings("ignore")

import matplotlib.pyplot as plt
import matplotlib
import networkx as nx

matplotlib.use('Agg')
plt.ioff()

from utilities import *

def parse_args(args):
    parser = argparse.ArgumentParser(description='Prints module radii stat from xdb')
    return parser.parse_args(args)

def show_graph_with_labels(adjacency_matrix, labels):
    labels_dict = {i: v for i, v in enumerate(labels)}
    adjacency_matrix = np.asarray(adjacency_matrix)

    G = nx.from_numpy_matrix(adjacency_matrix)
    D = nx.degree(G)
    D = [(D[node]+1) * 20 for node in G.nodes()]

    fig_size = 13
    plt.figure(figsize=(fig_size, fig_size))

    pos = nx.spring_layout(G, k=2)

    nx.draw(G,
        pos,
        node_size=[5 * v for v in D],
        labels=labels_dict,
        font_size=16)
    plt.axis('equal')

    plt.show(block=False)
    plt.savefig('xdb_adj_mat.png')

def main(test_args=None):
    args = parse_args(sys.argv[1:] if test_args is None else test_args)

    xdb = read_json('resources/xdb.json')

    # Print centre-of-mass stats
    (avg_d, min_d, max_d) = com_dist_info(xdb)
    print('Distances avg: {}, min: {}, max: {}'.format(avg_d, min_d, max_d))

    # Print adjacency matrix
    singles = xdb['modules']['singles']
    hubs = xdb['modules']['hubs']

    n_singles = len(singles)
    n_hubs = len(hubs)
    n_modules = n_singles + n_hubs

    all_names = list(singles.keys()) + list(hubs.keys())
    name_to_idx = {name: i for i, name in enumerate(all_names)}

    adjmat = [[0] * n_modules for _ in range(0, n_modules)]

    # print('-----------Adjacency Matrix-----------')

    for tx in xdb['n_to_c_tx']:
        mod_a, mod_b = tx['mod_a'], tx['mod_b']
        id_a, id_b = name_to_idx[mod_a], name_to_idx[mod_b]
        adjmat[id_a][id_b] = 1.0
        adjmat[id_b][id_a] = 1.0
        # print(','.join((mod_a, mod_b)))

    show_graph_with_labels(adjmat, all_names)
    
    # print('Names:')
    # print(','.join(all_names))

    # for row in adjmat:
    #     print(','.join((str(i) for i in row)))

if __name__ =='__main__': 
    safe_exec(main)