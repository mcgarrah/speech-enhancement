import os
import time

import torch
import wandb

CHECKPOINT_DIR = "checkpoints"


def load(checkpoint_filename, net=None, use_cuda=True):
    checkpoint_path = os.path.join(CHECKPOINT_DIR, checkpoint_filename)
    map_location = None if use_cuda else torch.device("cpu")
    if checkpoint_filename.endswith("full.ckpt"):
        net = torch.load(checkpoint_path, map_location=map_location)
    else:
        assert net, "A model is required for loading a state dict checkpoint."
        state_dict = torch.load(checkpoint_path, map_location=map_location)
        net.load_state_dict(state_dict)

    return net.cuda() if use_cuda else net.cpu()


def save(net, prefix, name=None, use_wandb=False):
    """
    Save full model checkpoint to disk
    """
    checkpoint_filename = get_checkpoint_filename(prefix, name, suffix="full.ckpt")
    print(f"\nSaving checkpoint model as {checkpoint_filename}\n")
    checkpoint_path = os.path.join(CHECKPOINT_DIR, checkpoint_filename)
    torch.save(net, checkpoint_path)

    if use_wandb:
        # Upload model to wandb
        print(f"Uploading {checkpoint_path} to W&B")
        wandb.save(checkpoint_path)

    return checkpoint_path


def save_state_dict(net, prefix, name=None, use_wandb=False):
    """
    Save model state dict checkpoint to disk
    """
    checkpoint_filename = get_checkpoint_filename(prefix, name, suffix="ckpt")
    print(f"\nSaving checkpoint state dict as {checkpoint_filename}\n")
    checkpoint_path = os.path.join(CHECKPOINT_DIR, checkpoint_filename)
    torch.save(net.state_dict(), checkpoint_path)
    if use_wandb:
        # Upload model to wandb
        print(f"Uploading {checkpoint_path} to W&B")
        wandb.save(checkpoint_path)

    return checkpoint_path


def get_checkpoint_filename(prefix, name, suffix):
    if name:
        return f"{prefix}-{name}-{int(time.time())}.{suffix}"
    else:
        return f"{prefix}-{int(time.time())}.{suffix}"
