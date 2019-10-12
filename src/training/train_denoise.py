"""
Training loop for speech denoiser
"""
import torch
import torch.optim as optim
import torch.nn as nn
from tqdm import tqdm
from torch.utils.data import DataLoader
import wandb

from ..datasets.speech_dataset import SpeechDataset
from ..models.denoise_net import SpeechDenoiseNet
from ..models.scene_net import SceneNet
from ..utils.moving_average import MovingAverage
from ..utils.feature_loss import AudioFeatureLoss
from ..utils.checkpoint import save_checkpoint

USE_WANDB = False
USE_CUDA = True
NUM_EPOCHS = 100
CHECKPOINT_EPOCHS = 10
LEARNING_RATE = 1e-4
ADAM_BETAS = (0.9, 0.999)
WEIGHT_DECAY = 1e-2
BATCH_SIZE = 32
LOSS_NET_CHECKPOINT = (
    "checkpoints/scene-net-denoiser-loss-split-up-conv-layers-2-1570666708.ckpt"
)

WANDB_NAME = None
if USE_WANDB:
    WANDB_NAME = input("What do you want to call this run: ")
    WANDB_PROJECT = "speech-denoise-net"
    wandb.init(
        name=WANDB_NAME or None,
        project=WANDB_PROJECT,
        config={
            "Epochs": NUM_EPOCHS,
            "Learning Rate": LEARNING_RATE,
            "Adam Betas": ADAM_BETAS,
            "Weight Decay": WEIGHT_DECAY,
            "Batch Size": BATCH_SIZE,
        },
    )

# Load datasets
training_set = SpeechDataset(train=True)
clean = []
noisy = []
for _ in range(5):
    clean = [*training_set.clean_data, *clean]
    noisy = [*training_set.noisy_data, *noisy]

training_set.clean_data = clean
training_set.noisy_data = noisy
validation_set = SpeechDataset(train=False)

# Construct data loaders
training_data_loader = DataLoader(
    training_set, batch_size=BATCH_SIZE, shuffle=True, num_workers=3
)
validation_data_loader = DataLoader(
    validation_set, batch_size=BATCH_SIZE, shuffle=True, num_workers=3
)

# Initialize model
net = SpeechDenoiseNet().cuda() if USE_CUDA else SpeechDenoiseNet().cpu()
if USE_WANDB:
    wandb.watch(net)

# Initialize loss function, optimizer
loss_net = SceneNet().cuda()
loss_net.load_state_dict(torch.load(LOSS_NET_CHECKPOINT))
loss_net.eval()
criterion = AudioFeatureLoss(loss_net)
optimizer = optim.AdamW(
    net.parameters(), lr=LEARNING_RATE, betas=ADAM_BETAS, weight_decay=WEIGHT_DECAY
)

# Keep track of loss history using moving average
training_loss = MovingAverage(decay=0.8)
validation_loss = MovingAverage(decay=0.8)
# Baseline of ~0.01 for no change, ~1 for random noise.
mean_squared_error = nn.MSELoss()
training_mse = MovingAverage(decay=0.8)
validation_mse = MovingAverage(decay=0.8)

for epoch in range(NUM_EPOCHS):
    print(f"\nEpoch {epoch + 1} / {NUM_EPOCHS}\n")
    if epoch % CHECKPOINT_EPOCHS == 0:
        checkpoint_path = save_checkpoint(net, "denoise-net", name=WANDB_NAME)

    # Run training loop
    net.train()
    for inputs, targets in tqdm(training_data_loader):
        # Add channel dimension to input
        batch_size = inputs.shape[0]
        audio_length = inputs.shape[1]
        inputs = inputs.view(batch_size, 1, -1)

        # Tell PyTorch to reset gradient tracking for new training run.
        optimizer.zero_grad()

        # Get a prediction from the model
        inputs = inputs.cuda() if USE_CUDA else inputs.cpu()
        outputs = net(inputs)
        assert outputs.shape == (batch_size, audio_length)

        # Run loss function on over the model's prediction
        targets = targets.cuda() if USE_CUDA else targets.cpu()
        assert targets.shape == (batch_size, audio_length)
        loss = criterion(outputs, targets)

        # Calculate model weight gradients from the loss
        loss.backward()

        # Update model weights via gradient descent.
        optimizer.step()

        # Track training information
        mse = mean_squared_error(outputs, targets).data.item()
        training_mse.update(mse)
        loss_amount = loss.data.item()
        training_loss.update(loss_amount)

    criterion.epoch()

    # Check performance (loss) on validation set.
    net.eval()
    with torch.no_grad():
        for inputs, targets in tqdm(validation_data_loader):
            batch_size = inputs.shape[0]
            audio_length = inputs.shape[1]
            inputs = inputs.view(batch_size, 1, -1)
            inputs = inputs.cuda() if USE_CUDA else inputs.cpu()
            targets = targets.cuda() if USE_CUDA else targets.cpu()
            outputs = net(inputs)
            loss = criterion(outputs, targets)
            loss_amount = loss.data.item()
            validation_loss.update(loss_amount)
            mse = mean_squared_error(outputs, targets).data.item()
            validation_mse.update(mse)

    # Log training information for epoch.
    training_info = {
        "Training Loss": training_loss.value,
        "Validation Loss": validation_loss.value,
        "Training MSE": training_mse.value,
        "Validation MSE": validation_mse.value,
    }
    print("")
    for k, v in training_info.items():
        s = "{k: <20}{v:0.4f}".format(k=k, v=v)
        print(s)
    if USE_WANDB:
        wandb.log(training_info)


# Save final model checkpoint
checkpoint_path = save_checkpoint(net, "denoise-net", name=WANDB_NAME)
# Upload model to wandb
if USE_WANDB:
    wandb.save(checkpoint_path)
