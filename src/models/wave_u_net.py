import torch
from torch import nn
from torch.nn.utils import weight_norm


# Benchmarks taken with 1024 sample dataset
# -----------------------------------------------------------------------
# Batch |   Audio   |   Checkpoints |   Memory |    Epoch   |   Loss    |
# -----------------------------------------------------------------------
# 32        2**15       0               2.6GB       14s         speech mse
# 32        2**15       0               5.0GB       14s         speech + noise mse
# 64        2**15       0               5.2GB       14s         speech mse
# 128       2**15       0               OOM         x           speech mse
# 32        2**15       4               2.0GB       13s         speech mse
# 64        2**15       4               3.9GB       13s         speech mse
# 128       2**15       4               OOM         x           speech mse
# 128       2**15       8               OOM         x           speech mse
# 128       2**15       12              OOM         x           speech mse
# 128       2**14       12              2GB         7s          speech mse
# 256       2**14       12              OOM         x           speech mse
# 256       2**14       16              OOM         x           speech mse
# 176       2**14       16              ???         7s          speech mse


"""
We use the same VCTK dataset

ADAM optimization algorithm, a learning rate of 0.0001, decay rates β1 = 0.9 and β2 = 0.999
a batch size of 16.

We specify an initial network layer size of 12
16 extra filters per layer are also specified,
with downsampling block filters of size 15 and upsampling block filters of size 5 like in [12].

We train for 2,000 iterations with mean squared error (MSE) over all source output samples in a batch as
loss and apply early stopping if there is no improvement on the validation set for 20 epochs.

We use a fixed validation set of 10 randomly selected tracks. 

Then, the best model is fine-tuned with the batch size doubled and 
the learning rate lowered to 0.00001, again until 20 epochs have passed without
improved validation loss.

Under our implementation, training took c.36 hours using GeForce GTX 1080 Ti GPU with 11178 MiB

Train and test datasets provided by the 28-speaker 
[Voice Bank Corpus (VCTK)](https://datashare.is.ed.ac.uk/handle/10283/2791) [4]
(30 speakers in total - 28 intended for training and 2 reserved for testing).
 The noisy training data were generated by mixing the clean data with various noise datasets, 
 as per the instructions provided in [4, 5, 6].



audio-based MSE loss and mono
signals downsampled to 8192 Hz


"""

NUM_C = 24  # Factor which determines the number of channels
NUM_ENCODER_LAYERS = 12


class WaveUNet(nn.Module):
    """
    Convolutional neural net for speech enhancement
    Proposed in Improved Speech Enhancement with the Wave-U-Net (https://arxiv.org/pdf/1811.11307.pdf),
    which builds upon this paper (https://arxiv.org/pdf/1806.03185.pdf)
    """

    def __init__(self):
        super().__init__()
        # Construct encoders
        self.encoders = nn.ModuleList()
        layer = ConvLayer(1, NUM_C, kernel=15)
        self.encoders.append(layer)
        for i in range(1, NUM_ENCODER_LAYERS):
            in_channels = i * NUM_C
            out_channels = (i + 1) * NUM_C
            layer = ConvLayer(in_channels, out_channels, kernel=15)
            self.encoders.append(layer)

        self.middle = ConvLayer(12 * NUM_C, 13 * NUM_C, kernel=15)

        # Construct decoders
        self.upsample = nn.Upsample(
            scale_factor=2, mode="linear", align_corners=True
        )
        self.decoders = nn.ModuleList()
        for i in reversed(range(1, NUM_ENCODER_LAYERS + 1)):
            in_channels = (2 * (i + 1) - 1) * NUM_C
            out_channels = i * NUM_C
            layer = ConvLayer(in_channels, out_channels, kernel=5)
            self.decoders.append(layer)

        # Extra dimension for input
        self.output = ConvLayer(NUM_C + 1, 1, kernel=1, nonlinearity=nn.Tanh)

    def forward(self, input_t):
        # Encoding
        # (b, 1, 16384)
        acts = input_t
        skip_connections = []
        for encoder in self.encoders:
            acts = encoder(acts)
            skip_connections.append(acts)
            # Decimate activations
            acts = acts[:, :, ::2]

        # (b, 288, 4)
        acts = self.middle(acts)
        # (b, 312, 4)

        # Decoding
        skip_connections = list(reversed(skip_connections))
        for idx, decoder in enumerate(self.decoders):
            # Upsample in the time direction by a factor of two, using interpolation
            acts = self.upsample(acts)
            # Concatenate upsampled input and skip connection from encoding stage.
            # Perform the concatenation in the feature map dimension.
            skip = skip_connections[idx]
            acts = torch.cat((acts, skip), dim=1)
            acts = decoder(acts)

        # (b, 24, 16384)
        acts = torch.cat((acts, input_t), dim=1)
        output_t = self.output(acts)
        # (batch, 1, 16384) (or 1, 3, 5, etc.)
        return output_t


class ConvLayer(nn.Module):
    """
    Single convolutional layer with nonlinear output
    """

    def __init__(self, in_channels, out_channels, kernel, nonlinearity=nn.PReLU):
        super().__init__()
        self.nonlinearity = nonlinearity()
        conv = nn.Conv1d(
            in_channels=in_channels,
            out_channels=out_channels,
            kernel_size=kernel,
            padding=kernel // 2,  # Same padding
            bias=True,
        )
        self.conv = weight_norm(conv)
        # Apply Kaiming initialization to convolutional weights
        nn.init.xavier_uniform_(self.conv.weight)

    def forward(self, input_t):
        """
        Compute output tensor from input tensor
        """
        acts = self.conv(input_t)
        return self.nonlinearity(acts)
