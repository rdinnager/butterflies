from itertools import count

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader

from tqdm import tqdm

import random
random.seed(0)
torch.manual_seed(0)

import numpy as np

import sys
import time

from autoencoder import Autoencoder

from collections import deque

VARIATIONAL = False

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
AUTOENCODER_FILENAME = 'trained_models/autoencoder.to'

from image_loader import ImageDataset
dataset = ImageDataset()
BATCH_SIZE = 32

data_loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, num_workers=4)

autoencoder = Autoencoder()

if "continue" in sys.argv:    
    autoencoder.load_state_dict(torch.load(AUTOENCODER_FILENAME), strict=False)

autoencoder.train()

optimizer = optim.Adam(autoencoder.parameters(), lr=0.00005)
criterion = lambda a, b: torch.mean(torch.abs(a - b))

error_history = deque(maxlen=len(dataset) // BATCH_SIZE)

def kld_loss(mean, log_variance):
    return -0.5 * torch.sum(1 + log_variance - mean.pow(2) - log_variance.exp()) / mean.nelement()

def train():
    for epoch in count():
        batch_index = 0
        epoch_start_time = time.time()
        for sample in tqdm(data_loader):
            sample = sample.to(device)

            autoencoder.zero_grad()

            if VARIATIONAL:
                output, mean, log_variance = autoencoder.forward(sample)
                kld = kld_loss(mean, log_variance)
            else:
                output = autoencoder.decode(autoencoder.encode(sample))
                kld = 0

            reconstruction_loss = criterion(output, sample)
            error_history.append(reconstruction_loss.item())

            loss = reconstruction_loss + kld
            
            loss.backward()
            optimizer.step()
            batch_index += 1

        print("Epoch " + str(epoch) \
                + ': reconstruction loss: {0:.5f}'.format(sum(error_history) / len(error_history)) \
                + ', KLD loss: {0:.4f}'.format(kld))
    
        torch.save(autoencoder.state_dict(), AUTOENCODER_FILENAME)
        torch.save(autoencoder.state_dict(), 'trained_models/checkpoints/autoencoder_{:04d}.to'.format(epoch))

train()