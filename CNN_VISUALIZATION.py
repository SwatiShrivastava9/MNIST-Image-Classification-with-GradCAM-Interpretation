# -*- coding: utf-8 -*-
"""DAI_Assignment_1_task_2.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1ytoJU8x3JjtYYFNCypf3y3fDYXYm2ZzE
"""

# start by installing the pytorch-gradcam module
!pip install -q grad-cam==1.4.3

import os
from tqdm import tqdm
from glob import glob
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report
from sklearn.model_selection import KFold, train_test_split
import torch
import torchvision
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torch.utils.data import SubsetRandomSampler, ConcatDataset
from torch.utils.data import random_split
from torchvision.io import read_image
from torchvision import transforms as t


# GradCAM implementation
from pytorch_grad_cam import GradCAM, HiResCAM, ScoreCAM, GradCAMPlusPlus, AblationCAM, XGradCAM, EigenCAM, FullGrad, LayerCAM, EigenGradCAM
from pytorch_grad_cam.utils.model_targets import ClassifierOutputSoftmaxTarget
from pytorch_grad_cam.utils.image import show_cam_on_image

def random_split_ratio(dtaset, test_size=.2, random_state=None):
    L = len(dtaset)
    n_scnd = int(L*test_size)
    n_first = L - n_scnd
    if random_state:
        frst_split, scnd_split = random_split(dtaset, lengths=[n_first, n_scnd], generator=torch.Generator().manual_seed(random_state))
    else:
        frst_split, scnd_split = random_split(dtaset, lengths=[n_first, n_scnd])

    return frst_split, scnd_split

def evaluate(dtaset, model, device='cpu', **dataloader_args):
    dataloader = DataLoader(dtaset, **dataloader_args)
    preds = []
    labels = []
    with torch.no_grad():
        model.eval()
        model.to(device)

        for x_batch, y_batch in tqdm(dataloader):
            x_batch = x_batch.to(device)
            y_batch = y_batch.tolist()

            outs = model(x_batch).detach().cpu()
            predictions = torch.argmax(torch.softmax(outs, 1), 1).tolist()

            # extend the `preds` and `labels` lists with predictions and true labels
            preds.extend(predictions)
            labels.extend(y_batch)

    report = classification_report(labels, preds, digits = 3)
    print(report)
    return report

def train_cv(model_, loss_fn_, optimizer_, train_loader, val_loader, return_model=False, device='cpu', epochs=10, **opt_args):

    if train_loader.sampler:
        n_train = len(train_loader.sampler)
        n_val = len(val_loader.sampler)
    else:
        n_train = len(train_loader.dataset)
        n_val = len(val_loader.dataset)

    training_losses = []
    validation_losses = []

    # initialize the model, optimizer, and loss function
    model = model_()
    loss_fn = loss_fn_()
    optimizer = optimizer_(model.parameters(), **opt_args)

    model.to(device)

    print("Number of samples")
    print("Training:", n_train)
    print('Validation:', n_val)
    for epoch in range(epochs):
        # define running losses
        epoch_training_running_loss = 0
        epoch_val_running_loss = 0

        # loop through every batch in the training loader
        for x_batch, y_batch in tqdm(train_loader):

            x_batch, y_batch = x_batch.to(device), y_batch.to(device)


            optimizer.zero_grad(set_to_none=True)

            # get the model outputs and calculate the loss
            outs = model(x_batch)
            loss = loss_fn(outs, y_batch)

            # calculate the gradients and apply an optimization step
            loss.backward()
            optimizer.step()

            epoch_training_running_loss += (loss.item() * x_batch.size(0))

        with torch.no_grad():
            model.eval()
            for x_batch, y_batch in tqdm(val_loader):
                x_batch, y_batch = x_batch.to(device), y_batch.to(device)

                outs = model(x_batch)
                loss = loss_fn(outs, y_batch)

                epoch_val_running_loss += (loss.item() * x_batch.size(0))
            model.train()

        average_training_loss = epoch_training_running_loss / n_train
        average_validation_loss = epoch_val_running_loss / n_val

        training_losses.append(average_training_loss)
        validation_losses.append(average_validation_loss)

        print(f"epoch {epoch+1}/{epochs} | avg. training loss: {average_training_loss:.3f}, avg. validation loss: {average_validation_loss:.3f}")

    # return the training and validation losses, also return the model if return_model is True
    if return_model:
        return training_losses, validation_losses, model
    else:
        return training_losses, validation_losses

def gradcam(model, gradcam_obj, layers, targets, dataset, N=5, use_cuda=False, show_labels=False, idx_to_label=None, **gradcam_params):
    random_indices = np.random.randint(0, len(dataset), N)
    samples = [dataset[idx][0].unsqueeze(0) for idx in random_indices]
    input_tensor = torch.cat(samples, dim=0)

    if show_labels:
        labels = [dataset[idx][1].item() for idx in random_indices]
        if idx_to_label:
            labels = [idx_to_label[label] for label in labels]

    for idx, layer in enumerate(layers):
        target_layers = [layer]


        cam = gradcam_obj(model=model, target_layers=target_layers, use_cuda=use_cuda)


        grayscale_cam = cam(input_tensor=input_tensor, targets=targets, **gradcam_params)

        images = [input_tensor[idx].permute(1,2,0).numpy() for idx in range(N)]
        grayscaled_cam = [grayscale_cam[idx,:] for idx in range(N)]
        heatmaps_on_inputs = [show_cam_on_image(img, cam) for img,cam in zip(images, grayscaled_cam)]

        viz_img_list = [images, grayscaled_cam, heatmaps_on_inputs]
        subfig_titles = ["Input Images", "Grayscaled Heatmap", "Heatmaps on the Inputs"]

        fig = plt.figure(figsize=(20, 10))
        subfigs = fig.subfigures(nrows=3, ncols=1)

        fig.suptitle(f'GradCAM for layer: {idx+1}', fontsize=18, y=1.05)
        for subfig_idx, subfig in enumerate(subfigs):
            subfig.suptitle(subfig_titles[subfig_idx], y=1)

            viz_list = viz_img_list[subfig_idx]

            axs = subfig.subplots(nrows=1, ncols=N)
            for idx in range(N):
                axs[idx].imshow(viz_list[idx], cmap='gray')

                if show_labels:
                    axs[idx].set_title(labels[idx])

                axs[idx].set(xticklabels=[], yticklabels=[], xticks=[], yticks=[])

        plt.show()

        print('-'*150)
        print("\n\n")

from google.colab import drive

drive.mount('/content/drive')

#file_path = '/content/drive/My Drive/DAI_Assign1/diabetes.csv'

# read the training and test datasets
DATASET_PATH = '/content/drive/My Drive/DAI_Assign1'
train_csv = pd.read_csv(os.path.join(DATASET_PATH, 'mnist_train.csv'))
test_csv = pd.read_csv(os.path.join(DATASET_PATH, 'mnist_test.csv'))

# split the training dataset to construct a validation set
train_set, val_set = train_test_split(train_csv, test_size=.2)
test_set = test_csv.copy()

class MNISTDataset(Dataset):
    #Use the _initialize method to reshape and define the input and target data
    def __init__(self, dataframe, transformations=None):
        self._dataframe = dataframe
        self.transformations = transformations
        self.inputs = None
        self.targets = None

        if dataframe.shape[1] == 785: # if it has one more column besides the pixels, it is the training set
            self.dataset_type = 'training'
        else:
            self.dataset_type = 'test'

        self._initialize()

    def _initialize(self):
        if self.dataset_type == 'training':
            self.inputs = self._dataframe.iloc[:, 1:].values.reshape(-1,1, 28, 28)
            self.targets = self._dataframe.iloc[:, 0].values
        else:
            self.inputs = self._dataframe.values.reshape(-1, 1, 28, 28)

    def __len__(self):
        return len(self._dataframe)

    def __getitem__(self, idx):
        x = self.inputs[idx]
        if self.transformations:
            x = self.transformations(x)
        else:
            x = x/255.
            x = torch.tensor(x, dtype=torch.float32)


        if self.dataset_type == 'training':
            y = self.targets[idx]
            y = torch.tensor(y, dtype=torch.long)
            return x,y
        else:
            return x



train_dataset = MNISTDataset(train_set)

test_dataset = MNISTDataset(test_set)
val_dataset = MNISTDataset(val_set)

train_loader = DataLoader(train_dataset, batch_size=512, shuffle=True)
test_loader = DataLoader(test_dataset, batch_size=512, shuffle=False)

class CNN(nn.Module):
    def __init__(self):
        super().__init__()

        self.cnn_block1 = nn.Sequential(
            nn.Conv2d(in_channels=1, out_channels=32, kernel_size=3, stride=2, padding=0, dilation=1, groups=1, bias=False), # output shape = (batch, 32, 13, 13)
            nn.BatchNorm2d(num_features=32),
            nn.ReLU()
        )
        self.cnn_block2 = nn.Sequential(
            nn.Conv2d(in_channels=32, out_channels=64, kernel_size=3, stride=1, padding=0, dilation=1, groups=1, bias=False), # output shape = (batch, 64, 11, 11)
            nn.BatchNorm2d(num_features=64),
            nn.ReLU()
        )
        self.cnn_block3 = nn.Sequential(
            nn.Conv2d(in_channels=64, out_channels=128, kernel_size=3, stride=1, padding=0, dilation=1, groups=1, bias=False), # output shape = (batch, 128, 9, 9)
            nn.BatchNorm2d(num_features=128),
            nn.ReLU()
        )

        self.fc_layer = nn.Linear(128*9*9, 10)

    def forward(self, x):
        x = self.cnn_block1(x)
        x = self.cnn_block2(x)
        x = self.cnn_block3(x)

        # flatten the processed tensor for linear layer
        x = x.view(x.shape[0], -1) # (batch, 128*9*9)
        out = self.fc_layer(x)
        return out

loss_fn = nn.CrossEntropyLoss
optimizer = torch.optim.Adam
model_ = CNN
device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

print("Training on ", device)


training_losses, validation_losses = train_cv(model_, loss_fn, optimizer, train_loader=train_loader, val_loader=test_loader, device=device, epochs=10, lr=1e-3)

training_loader = DataLoader(train_dataset, batch_size=512, shuffle=True)
val_loader = DataLoader(val_dataset, batch_size=512, shuffle=False)

training_losses, validation_losses, model = train_cv(model_, loss_fn, optimizer, training_loader, val_loader, device=device, return_model=True, epochs=10, lr=1e-3)

plt.title('Performance')
plt.plot(training_losses, label='training loss')
plt.plot(validation_losses, label='validation loss')
plt.legend()
plt.show()

print("Training report")
train_report = evaluate(train_dataset, model, device=device, batch_size=512)
print("Validation report")
val_report = evaluate(val_dataset, model, device=device, batch_size=512)

cnn_layers = [model.cnn_block1,  model.cnn_block2, model.cnn_block3]

val_dataset = MNISTDataset(val_set)

targets = [ClassifierOutputSoftmaxTarget(i) for i in range(10)]

gradcam(model, GradCAM, cnn_layers, targets, val_dataset, aug_smooth=True, eigen_smooth=True, use_cuda=False)