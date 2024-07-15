# code to generate figures 6 and 7 in the paper
import os, io
import re
import random
import urllib.request 

import numpy as np
import pandas as pd
from ast import literal_eval
from collections import Counter

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.cm as cm
import seaborn as sns
from mpl_toolkits.mplot3d import Axes3D
from umap import UMAP

import scipy
from scipy.cluster.hierarchy import ward, fcluster
import scipy.cluster.hierarchy as sch
from scipy.spatial.distance import squareform, pdist
from scipy_cut_tree_balanced import cut_tree_balanced

import sklearn.metrics as metrics
from sklearn.metrics.pairwise import pairwise_distances
from sklearn.metrics.cluster import adjusted_rand_score

import plotly.express as px
import plotly.offline as py
import plotly.graph_objs as go
import plotly.express as px




def check_symmetric(arr):
    if arr.shape[0] != arr.shape[1]:
        raise ValueError("The given array is not square!")

    non_symmetric_indices = []
    n = arr.shape[0]
    for i in range(n):
        for j in range(i+1, n):  # Only check the upper triangle
            if arr[i, j] != arr[j, i]:
                non_symmetric_indices.append((i, j))

    return non_symmetric_indices

def make_symmetric(mat):
    rows, cols = mat.shape
    for i in range(rows):
        for j in range(i + 1, cols):  # only consider upper triangular part
            if mat[i, j] != mat[j, i]:  # unsymmetrical
                # Take the minimum of the two unsymmetrical entries
                symmetric_value = min(mat[i, j], mat[j, i])
                mat[i, j] = symmetric_value
                mat[j, i] = symmetric_value
    return mat




def cluster_purity(cluster_id, clusters, assigned_labels):
    assigned_labels = np.array(assigned_labels)
    unique, counts = np.unique(assigned_labels[np.where(clusters == cluster_id)[0]], return_counts=True)
    return counts.max() / np.where(clusters == cluster_id)[0].shape[0]

def weighted_average_purity(assigned_labels, clusters):
    unique_clusters = np.unique(clusters)
    total_weight = len(assigned_labels)
    total_sum = sum(cluster_purity(cluster_id, clusters, assigned_labels) * np.where(clusters == cluster_id)[0].shape[0] for cluster_id in unique_clusters)
    return total_sum / total_weight

def cluster_entropy(cluster_id, clusters, assigned_labels):
    assigned_labels = np.array(assigned_labels)
    n = len(np.unique(assigned_labels))
    proportions = np.array([np.sum(assigned_labels[np.where(clusters == cluster_id)[0]] == label) for label in np.unique(assigned_labels)]) / np.where(clusters == cluster_id)[0].shape[0]
    entropy_terms = [-p * np.log2(p) if p > 0 else 0 for p in proportions]
    entropy = sum(entropy_terms)
    return entropy / np.log2(n)

def weighted_average_entropy(assigned_labels, clusters):
    unique_clusters = np.unique(clusters)
    total_weight = len(assigned_labels)
    total_sum = sum(cluster_entropy(cluster_id, clusters, assigned_labels) * np.where(clusters == cluster_id)[0].shape[0] for cluster_id in unique_clusters)
    return total_sum / total_weight

#for each Target retrieve info about Activity and Factor
marks = pd.read_excel("./data/target_activity_factor.xlsx") 
marks.columns = ["Target", "Activity", "Factor"]
marks['Activity'].value_counts()
marks['Factor'].value_counts()

#retrieve hg38-aligned dataset metadata
df38 = pd.read_csv("./data/genome_df38.csv", delimiter=",")
df38 = pd.DataFrame(df38)
df38 = df38.loc[:, ['Accession', 'Target', 'Biosample term name', 'Genome']]
df38['Target'].value_counts()
df38['Biosample term name'].value_counts()
merged_df = pd.merge(df38, marks, on='Target')

#get hierarchical clustering linkages fro all 23 chrs (23rd is X chr)
list_linkages = []
for i in range(1, 24):
    chr_id = i
    if chr_id == 23: #this is chromosome X
        chr_id = 'X'
    df_corr = pd.read_csv("./results38/hg38_chr" + str(chr_id) + "_200data" + 'correlation.h5', index_col=0)
    cor_dist = df_corr.to_numpy()
    np.fill_diagonal(cor_dist, 0)
    indices = check_symmetric(cor_dist)
    if len(indices) != 0:
        cor_dist = make_symmetric(cor_dist)
    condensed_dist = squareform(cor_dist)
    linkresult = sch.linkage(condensed_dist, method  = "complete")
    linkresult[linkresult < 0] = 0
    list_linkages.append(linkresult)


#producing the FIGURE 6 in the paper
colors = list(cm.tab20(np.linspace(0, 1, 20)))
additional_colors = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]  
colors += additional_colors
plt.figure(figsize=(10, 6))
fl = 14
for i in range(0, 23):
    chr_id = i + 1
    linkresult = list_linkages[i]
    distances = linkresult[:, 2]   
    distances = np.arange(2, 0, -0.1) 
    num_clusters = []
    for dist in distances:
        clusters = fcluster(linkresult, dist, criterion='distance')
        unique_clusters = np.unique(clusters)
        num_clusters.append(len(unique_clusters))
    if chr_id != 23:
        plt.plot(distances, np.log10(num_clusters), '-o', label=f"Chr {chr_id}", color=colors[i])
    else:
        plt.plot(distances, np.log10(num_clusters), '-o', label="Chr X", color=colors[i])    
plt.title('Number of Clusters vs. Distance', fontsize=20)
plt.xlabel('Distance', fontsize=fl)
plt.ylabel('Logarithm of the Number of Clusters', fontsize=fl)
plt.xticks(fontsize=14)
plt.yticks(fontsize=14)
plt.legend(loc='lower left', bbox_to_anchor=(0.0, 0.0), ncol=4, fontsize = 9)
plt.grid(True)
plt.savefig("./results38/entropy_clusters_paper_plot_hg38.eps", format='eps')
#plt.show()



#producing FIGURE 7 in the paper
random.seed(2023)
labels_mark = list(merged_df['Target'])
labels_cell = list(merged_df['Biosample term name'])
labels_factor = list(merged_df['Factor'])
labels_activity = list(merged_df['Activity'])

colors = list(cm.tab20(np.linspace(0, 1, 20)))
additional_colors = [(1, 0, 0), (0, 1, 0), (0, 0, 1)]  
colors += additional_colors
distances = np.arange(2, 0, -0.1)

# function to perform the plotting for a given set of labels
def plot_for_labels(labels, ax, title):
    all_wa = []
    labels_true_wa = []
    for i in range(0, 23):
        chr_id = i + 1
        linkresult = list_linkages[i]
        wa = []
        true_wa = []
        for dist in distances:
            clusters = fcluster(linkresult, dist, criterion='distance')
            true_wa.append(weighted_average_entropy(labels, clusters))
            wa_values = []
            for j in range(100):
                random_labels = labels.copy()
                random.shuffle(random_labels)
                wa_values.append(weighted_average_entropy(random_labels, clusters))
            wa.append(np.mean(wa_values))
        all_wa.append(wa)
        color = colors[i]
        labels_true_wa.append(true_wa)
        if chr_id != 23:
            ax.plot(distances, true_wa, '-o', label=f"Chr {chr_id}", color=color)
        else:
            ax.plot(distances, true_wa, '-o', label="Chr X", color=color)
    mean_wa_all = np.mean(all_wa, axis=0)
    var_wa_all = np.var(all_wa, axis=0)
    ax.errorbar(distances, mean_wa_all, yerr=np.sqrt(var_wa_all), fmt='-o', label="Random", color="black")
    ax.set_title(title)
    ax.set_xlabel('Distance: (1 - correlation coefficient)')
    ax.set_ylabel('Weighted average of the normalized entropy')
    ax.grid(True)
    return all_wa, labels_true_wa


#fig, axes = plt.subplots(2, 2, figsize=(24, 24)) 

# plot_results = {}

# # Plot for each label type and store the results
# plot_results['Activity'] = plot_for_labels(labels_activity, axes[0, 0], 'Activity: Weighted average entropy vs. Distance')
# plot_results['Factor'] = plot_for_labels(labels_factor, axes[0, 1], 'Factor: Weighted average entropy vs. Distance')
# plot_results['Modification'] = plot_for_labels(labels_mark, axes[1, 0], 'Modification: Weighted average entropy vs. Distance')
# plot_results['Cell'] = plot_for_labels(labels_cell, axes[1, 1], 'Cell: Weighted average entropy vs. Distance')

# Create a common legend
# handles, labels = axes[0, 0].get_legend_handles_labels()
# fig.legend(handles, labels, loc='lower center', bbox_to_anchor=(0.5, 0.0), ncol=8)

# plt.tight_layout(rect=[0, 0.03, 1, 0.95])
# plt.show()
# plt.savefig("entropy_paper_plot_hg38.eps", format='eps')
# with open('/Users/akim/Documents/epi/plot_results.json', 'w') as file:
#     json.dump(plot_results, file)

#uncomment the block above to generate plot_results, can take several hours
#otherwise we load saved files with the results above
with open('./data/plot_results_38.json', 'r') as file:
    plot_results = json.load(file)

# Plot for each label type and store the results
plot_results['Activity'] = plot_for_labels(labels_activity, axes[0, 0], 'Activity: Weighted average entropy vs. Distance')
plot_results['Factor'] = plot_for_labels(labels_factor, axes[0, 1], 'Factor: Weighted average entropy vs. Distance')
plot_results['Modification'] = plot_for_labels(labels_mark, axes[1, 0], 'Modifier: Weighted average entropy vs. Distance')
plot_results['Cell'] = plot_for_labels(labels_cell, axes[1, 1], 'Cell: Weighted average entropy vs. Distance')

# Define distances (assuming these are already defined, in our case from 0 to 2 for 1 - correlation)
colors = list(cm.tab20(np.linspace(0, 1, 20))) + [(1, 0, 0), (0, 1, 0), (0, 0, 1)]
distances = np.arange(2, 0, -0.1)

fig, axes = plt.subplots(2, 2, figsize=(30, 30)) 
font_size = 22 
for idx, ((label, (all_wa, labels_true_wa)), ax) in enumerate(zip(plot_results.items(), axes.flatten())):
    for i, true_wa in enumerate(labels_true_wa):
        ax.plot(distances, true_wa, '-o', color=colors[i])
        
    # Plotting the random values with error bars (black curves)
    mean_random_wa = np.mean(all_wa, axis=0)
    std_random_wa = np.std(all_wa, axis=0)
    ax.errorbar(distances, mean_random_wa, yerr=std_random_wa, fmt='-o', color="black")
    ax.set_title(label, fontsize=30)
    ax.grid(True)
    if idx >= 2:  # Bottom plots
        ax.set_xlabel('Distance', fontsize=font_size)
    if idx % 2 == 0:  # Left plots
        ax.set_ylabel('Entropy', fontsize=font_size)
    ax.tick_params(axis='both', which='major', labelsize=20)

legend_handles = [mpatches.Patch(color=colors[i], label=f'Chr {i+1}' if i != 22 else 'Chr X') for i in range(23)]
legend_handles.append(mpatches.Patch(color="black", label="Random"))
fig.legend(handles=legend_handles, loc='lower center', bbox_to_anchor=(0.5, 0.0), ncol=12, fontsize = font_size)
plt.tight_layout(rect=[0, 0.05, 1, 0.95])
plt.savefig("./results38/entropy_paper_plot_hg38.eps", format='eps')

