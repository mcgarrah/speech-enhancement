import torch


class AudioFeatureLoss:
    """
    Custom loss function, where loss is the distance
    between two feature vectors produced by the supplied loss network
    """

    def __init__(self, loss_net):
        """
        Store loss net for use in calculating feature vectors.
        Loss net must accept a tensor (batch_size, 1, audio_length)
        And expose property `feature_layers` - which returns a list of weight vectors.
        """
        self.loss_net = loss_net

    def __call__(self, predicted_audio, target_audio):
        """
        Return single element loss tensor, containg loss value.
            predicted_audio is a tensor (batch_size, audio_length)
            target_audio is a tensor (batch_size, audio_length)
        """
        assert predicted_audio.shape == target_audio.shape
        assert len(predicted_audio.shape) == 2
        batch_size = predicted_audio.shape[0]
        predict_input = predicted_audio.view(batch_size, 1, -1)
        target_input = target_audio.view(batch_size, 1, -1)

        # create "features" method on loss net?
        _ = self.loss_net(predict_input)
        pred_feature_layers = self.loss_net.feature_layers
        _ = self.loss_net(target_input)
        target_feature_layers = self.loss_net.feature_layers

        # There is also some sort of weighting applied to each layer.
        # Skip this for now.
        loss_weights = 1.0
        # Sum up loss for each layer
        loss = torch.tensor([0.0], requires_grad=True).cuda()
        for idx in range(len(pred_feature_layers)):
            predicted_feature = pred_feature_layers[idx]
            target_feature = target_feature_layers[idx]
            loss[0] += l1_loss(predicted_feature, target_feature) / loss_weights

        return loss


def l1_loss(predicted_t, target_t):
    """
    Least absolute deviation / L1 loss function.
    Loss is defined as the sum of all the absolute  difference between the predicted and target values.

    Assume both input tensors have shape (batch_size, audio_length)
    """
    assert predicted_t.shape == target_t.shape
    assert len(predicted_t.shape) == 2
    diff_t = predicted_t - target_t
    return diff_t.abs().mean()
