"""
Evaluate a set of networks.
"""
import os
import sys

import torch
import numpy as np
from tqdm import tqdm
import matplotlib.pyplot as plt
from scipy.io import wavfile


from src.utils.checkpoint import load as load_checkpoint

from .dataset import SpeechEvaluationDataset

AUDIO_LENGTH = 2 ** 16  # ~1s of data at 16kHz
RESULT_DIR = "data/evaluation_results"
DATA_DIR = "data/speech_evaluation"
TEMPLATE_PATH = "src/datasets/speech_evaluation/template.html"
SNIPPET_PATH = "src/datasets/speech_evaluation/snippet.html"
CHECKPOINTS = [
    {
        "name": "U-net with GAN, MSE, feature loss",
        "file": "wave-u-net-mse-gan-feature-losses-1573224098.full.ckpt",
    },
    {
        "name": "U-net with GAN and feature loss",
        "file": "wave-u-net-new-baseline-1573206080.full.ckpt",
    },
    {
        "name": "U-net with feature loss",
        "file": "wave-u-net-feature-loss-only-1573203595.full.ckpt",
    },
    {"name": "U-net with MSE loss", "file": "wave-u-net-mse-onlyy-1573200273.full.ckpt"},
]
SAMPLES = [
    {"name": "Road noise", "slug": "road", "count": 4},
    {"name": "Cafe", "slug": "cafe", "count": 4},
    {"name": "Hiss", "slug": "hiss", "count": 4},
    {"name": "Machine", "slug": "machine", "count": 2},
    {"name": "Noise", "slug": "noise", "count": 2},
    {"name": "Outside", "slug": "outside", "count": 1},
    {"name": "Whine", "slug": "whine", "count": 1},
    {"name": "Music", "slug": "music", "count": 5},
    {"name": "Babbling speech", "slug": "babbling", "count": 3},
    {"name": "Clean", "slug": "clean", "count": 3},
]


def evaluate(checkpoints, samples):
    with open(SNIPPET_PATH, "r") as f:
        snippet = f.read()

    with open(TEMPLATE_PATH, "r") as f:
        template = f.read()

    print("Loading checkpoints")
    for checkpoint in checkpoints:
        name = checkpoint["name"]
        print(f"\tLoading checkpoint {name}")
        net = load_checkpoint(checkpoint["file"], use_cuda=False)
        net.eval()
        checkpoint["net"] = net

    snippets = []
    for sample in samples:
        sample_name = sample["name"]
        slug = sample["slug"]
        print(f"Checking sample {sample_name}")
        for sample_idx in range(1, sample["count"] + 1):
            print(f"\tChecking sample idx {sample_idx}")
            snippets.append(f'<h2 class="mt-4">{sample_name} #{sample_idx}</h2>')
            filename = f"{slug}.{sample_idx}.wav"
            file_path = os.path.join(DATA_DIR, filename)
            sample_rate, input_arr = wavfile.read(file_path)
            assert len(input_arr.shape) == 1
            assert sample_rate == 16000
            input_arr = pad_chunk(input_arr)
            sample_id = f"{slug}-{sample_idx}-input"
            save_audio_array(snippet, snippets, sample_id, "Input", input_arr)
            for checkpoint in checkpoints:
                checkpoint_name = checkpoint["name"]
                print(f"\t\tChecking net {checkpoint_name}")
                net = checkpoint["net"]
                pred_arr = get_prediction(net, input_arr)
                checkpoint_id = checkpoint["file"].split("."[0])
                sample_id = f"{slug}-{sample_idx}-{checkpoint_id}"
                save_audio_array(snippet, snippets, sample_id, checkpoint_name, pred_arr)

    html = template.format(inner="\n".join(snippets))
    with open(os.path.join("data", "speech_evaluation_report.html"), "w") as f:
        f.write(html)


def save_audio_array(snippet, snippets, sample_id, name, arr):
    save_dir = os.path.join(RESULT_DIR, sample_id)
    os.makedirs(save_dir, exist_ok=True)

    # Add files to snippets
    wav_path = os.path.join("evaluation_results", sample_id, "speech.wav")
    plot_path = os.path.join("evaluation_results", sample_id, "plot.png")
    snippets.append(snippet.format(name=name, wav_path=wav_path, plot_path=plot_path))

    # Save audio file
    save_filepath = os.path.join(save_dir, "speech.wav")
    wavfile.write(save_filepath, 16000, arr)

    # Save audio imagery
    save_filepath = os.path.join(save_dir, "plot.png")
    plt.ioff()
    fig, (ax1, ax2) = plt.subplots(ncols=2)
    fig.set_size_inches(16, 6)
    ax1.plot(arr)
    ax2.specgram(arr, Fs=16000)
    plt.savefig(save_filepath)
    plt.close(fig)


def get_prediction(net, input_arr):
    with torch.no_grad():
        inputs = torch.tensor(input_arr).float().cpu()
        inputs = inputs.view(1, 1, -1)
        outputs = net(inputs)
        outputs = outputs.squeeze(dim=0).squeeze(dim=0)
        return outputs.cpu().detach().numpy()


def pad_chunk(arr):
    """
    Pad sample length of audio, so that it's always
    the same size as all other samples (required for mini-batching)
    """
    size = (arr.size - arr.size % AUDIO_LENGTH) + AUDIO_LENGTH
    padding = size - arr.size
    arr = np.pad(arr, (0, padding))
    return arr


if __name__ == "__main__":
    evaluate(CHECKPOINTS, SAMPLES)
