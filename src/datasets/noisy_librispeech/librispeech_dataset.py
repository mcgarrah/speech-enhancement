import os
import random

import torchaudio
import torch
from tqdm import tqdm
from torch.utils.data import Dataset

from src.utils import s3
from src.datasets.s3dataset import S3BackedDataset

DATASET_NAME = "noisy_librispeech"
AUDIO_LENGTH = 2 ** 16  # ~4s of data at 16kHz


class NoisyLibreSpeechDataset(S3BackedDataset):
    """
    A dataset of clean and noisy speech, for use in the speech enhancement task.
    The input is a 1D tensor of floats, representing a complete noisy audio sample.
    The target is a 1D tensor of floats, representing a corresponding clean audio sample. 
    """

    def __init__(self, train, subsample=None, quiet=False):
        self.quiet = quiet
        super().__init__(dataset_name=DATASET_NAME, quiet=quiet)
        dataset_label = "train" if train else "test"
        itr = list if self.quiet else tqdm
        self.clean_data = []
        self.noise_data = []
        self.clean_folder = os.path.join(self.data_path, f"{dataset_label}_set")
        self.noise_folder = os.path.join(self.data_path, f"noise")
        self.clean_filenames = self.find_flac_filenames(self.clean_folder, subsample=subsample)
        self.noise_filenames = self.find_flac_filenames(self.noise_folder, subsample=subsample)
        if not quiet:
            print(f"Loading {dataset_label} dataset into memory.")
            print("Loading clean data...")

        for filename in itr(self.clean_filenames):
            path = os.path.join(self.clean_folder, filename)
            tensor, sample_rate = torchaudio.load(path)
            if tensor.nelement() < AUDIO_LENGTH:
                continue

            assert sample_rate == 16000
            assert tensor.dtype == torch.float32
            tensor = tensor.reshape(-1)
            self.clean_data.append(tensor)

        if not quiet:
            print("Loading noisy data...")

        for filename in itr(self.noise_filenames):
            path = os.path.join(self.noise_folder, filename)
            tensor, sample_rate = torchaudio.load(path)
            if tensor.nelement() < AUDIO_LENGTH:
                continue

            assert sample_rate == 16000
            assert tensor.dtype == torch.float32
            tensor = tensor[0, :].reshape(-1)
            self.noise_data.append(tensor)

        if not quiet:
            print("Done loading dataset into memory.")

    def __len__(self):
        """
        How many samples there are in the dataset.
        """
        return len(self.clean_data)

    def __getitem__(self, idx):
        """
        Get item by integer index,
        """
        clean = self.clean_data[idx]
        noise = random.choice(self.noise_data)
        clean_chunk = subsample_chunk_random(clean, AUDIO_LENGTH)
        noise_chunk = subsample_chunk_random(noise, AUDIO_LENGTH)
        noise_chunk = noise_chunk * random.randint(1, 10)
        noise_chunk[noise_chunk > 1] = 1
        noise_chunk[noise_chunk < -1] = -1
        noisy_chunk = clean_chunk + noise_chunk
        return clean_chunk, noisy_chunk


def subsample_chunk_random(tensor, chunk_width):
    """
    Randomly sample length of audio, so that it's always
    the same size as all other samples (required for mini-batching)
    """
    size = tensor.nelement()
    assert chunk_width < size
    chunk_start = random.randint(0, size - chunk_width + 1)
    return tensor[chunk_start : chunk_start + chunk_width]
