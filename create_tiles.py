from tkinter import *
import numpy as np
import json
from sklearn.cluster import KMeans
from itertools import count
from tqdm import tqdm
from PIL import Image, ImageDraw
import os
from multiprocessing import Pool
import traceback

codes = np.load('data/latent_codes_embedded.npy')
TILE_FILE_FORMAT = 'data/tiles/{:d}/{:d}/{:d}.jpg'

DEPTH_OFFSET = 8

TILE_SIZE = 256
IMAGE_SIZE = 128
TILE_DEPTH = 7

min_value = np.min(codes, axis=0)
max_value = np.max(codes, axis=0)
codes -= (max_value + min_value) / 2
codes /= np.max(codes, axis=0)

from image_loader import ImageDataset
dataset = ImageDataset()

codes_by_depth = []
hashes_by_depth = []

def create_tile(depth, x, y):
    tile_file_name = TILE_FILE_FORMAT.format(depth + DEPTH_OFFSET, x, y)
    if os.path.exists(tile_file_name):
        return
    
    tile = Image.new("RGB", (TILE_SIZE, TILE_SIZE), (255, 255, 255))

    codes_current = codes_by_depth[depth]
    hashes = hashes_by_depth[depth]

    if depth < TILE_DEPTH:
        for a in range(2):
            for b in range(2):
                old_tile_file_name = TILE_FILE_FORMAT.format(depth + 1 + DEPTH_OFFSET, x * 2 + a, y * 2 + b)
                image = Image.open(old_tile_file_name)
                image = image.resize((TILE_SIZE // 2, TILE_SIZE // 2), resample=Image.BICUBIC)
                tile.paste(image, (a * TILE_SIZE // 2, b * TILE_SIZE // 2))

    if depth > 0:
        margin = IMAGE_SIZE / 2 / TILE_SIZE
        x_range = ((x - margin) / 2**depth, (x + 1 + margin) / 2**depth)
        y_range = ((y - margin) / 2**depth, (y + 1 + margin) / 2**depth)

        mask = (codes_current[:, 0] > x_range[0]) \
            & (codes_current[:, 0] < x_range[1]) \
            & (codes_current[:, 1] > y_range[0]) \
            & (codes_current[:, 1] < y_range[1])
        indices = mask.nonzero()[0]

        positions = codes_current[indices, :]
        positions *= 2**depth * TILE_SIZE
        positions -= np.array((x * TILE_SIZE, y * TILE_SIZE))[np.newaxis, :]

        for i in range(indices.shape[0]):
            index = indices[i]
            image_file_name = 'data/images_alpha/{:s}.png'.format(hashes[index])
            image = Image.open(image_file_name)
            image = image.resize((IMAGE_SIZE, IMAGE_SIZE), resample=Image.BICUBIC)
            tile.paste(image, (int(positions[i, 0] - IMAGE_SIZE // 2), int(positions[i, 1] - IMAGE_SIZE // 2)), mask=image)
    
    tile_directory = os.path.dirname(tile_file_name)
    if not os.path.exists(tile_directory):
        os.makedirs(tile_directory)
    tile.save(tile_file_name)

def try_create_tile(*args):
    try:
        create_tile(*args)
    except:
        traceback.print_exc()
        exit()

def kmeans(points, n):
    if points.shape[0] <= n:
        for i in range (points.shape[0]):
            yield i
        return
    kmeans = KMeans(n_clusters=n)
    kmeans_clusters = kmeans.fit_predict(points)
    for i in range(n):
        center = kmeans.cluster_centers_[i, :]
        dist = np.linalg.norm(points - center[np.newaxis, :], axis=1)
        yield np.argmin(dist)

def get_circle_area_factor(x_range, y_range, k=10):
    points = np.meshgrid(
        np.linspace(x_range[0], x_range[1], k),
        np.linspace(y_range[0], y_range[1], k)
    )
    points = np.stack(points)
    points = points.reshape(2, -1).transpose()
    return np.count_nonzero(np.linalg.norm(points, axis=1) < 1) / k**2

def get_kmeans_indices(count, subdivisions):
    if subdivisions == 1:
        return np.array(list(kmeans(codes, count)), dtype=int)
    
    result = []
    for x in tqdm(range(subdivisions)):
        for y in range(subdivisions):
            x_range = (-1 + 2 * x / subdivisions, -1 + 2 * (x + 1) / subdivisions)
            y_range = (-1 + 2 * y / subdivisions, -1 + 2 * (y + 1) / subdivisions)

            mask = (codes[:, 0] > x_range[0]) \
                & (codes[:, 0] <= x_range[1]) \
                & (codes[:, 1] > y_range[0]) \
                & (codes[:, 1] <= y_range[1])
            indices = np.nonzero(mask)[0]
            codes_mask = codes[mask, :]
            for i in kmeans(codes_mask, int(count / subdivisions**2 * get_circle_area_factor(x_range, y_range))):
                result.append(indices[i])
    return np.array(result, dtype=int)

for depth in range(TILE_DEPTH):
    print("Running k-means for depth {:d}.".format(depth))
    number_of_items = 2**(2*depth) * 2
    indices = get_kmeans_indices(number_of_items, max(1, 2**(depth - 3)))
    hashes = [dataset.hashes[i] for i in indices]
    codes_by_depth.append(codes[indices, :])
    hashes_by_depth.append(hashes)

codes_by_depth.append(codes)
codes_by_depth.append(dataset.hashes)

worker_count = os.cpu_count()
print("Using {:d} processes.".format(worker_count))

for depth in range(TILE_DEPTH, -1, -1):
    pool = Pool(worker_count)
    progress = tqdm(total=(2**(2 * depth + 2)), desc='Depth {:d}'.format(depth + DEPTH_OFFSET))

    def on_complete(*_):
        progress.update()

    for x in range(-2**depth, 2**depth):
        tile_directory = os.path.dirname(TILE_FILE_FORMAT.format(depth + DEPTH_OFFSET, x, 0))
        if not os.path.exists(tile_directory):
            os.makedirs(tile_directory)
        for y in range(-2**depth, 2**depth):
            pool.apply_async(try_create_tile, args=(depth, x, y), callback=on_complete)
    pool.close()
    pool.join()