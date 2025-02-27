import torch
import numpy as np
from pathlib import Path
import os
import PlotUtils.PlotUtils as plot_utils
import DataLoaders.Unlabeled_dl as dl
import Backbones.ResNet as rn
import logging
import Models.SimSiam as sim_siam
import Models.BYOL as byol
logging.captureWarnings(True)
import time
from pl_bolts.optimizers.lr_scheduler import LinearWarmupCosineAnnealingLR
import Visualization.VisualizeConvFilters as visualize_filters


saved_models_path = os.path.join(os.getcwd(), "Trained_Models")
saved_plots_path = os.path.join(os.getcwd(), "Saved_Plots")
saved_eval_results_path = os.path.join(Path(os.getcwd()).parent, "Evaluation/Eval_Results")

def saveModel(epoch, model, optimizer, lr_scheduler, loss_dict, save_path):
    torch.save({
            'epoch': epoch,
            'model_state_dict': model.state_dict(),
            'optimizer_state_dict': optimizer.state_dict(),
        'lr_scheduler_state_dict':lr_scheduler.state_dict(),
        'loss_dict': loss_dict
    }, save_path)

def loadModel(model, optimizer, lr_scheduler, save_path, model_only=False):
    try:
        checkpoint = torch.load(save_path)
    except:
        print("No model file exists")
    model.load_state_dict(checkpoint['model_state_dict'])
    if model_only:
        return model
    epoch = checkpoint['epoch']
    model.load_state_dict(checkpoint['model_state_dict'])
    optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
    lr_scheduler.load_state_dict(checkpoint['lr_scheduler_state_dict'])
    loss_dict = checkpoint["loss_dict"]
    return epoch, model, optimizer, lr_scheduler, loss_dict


def plot_train_dict(train_dict, model_name, save_fp):
    save_fp_epochs = save_fp + "/" + model_name + "_EpochLosses"
    save_fp_iterations = save_fp + "/" + model_name + "_Iterations"
    epoch_losses = train_dict["epoch_losses"]
    plot_utils.plot(x_vals=range(1, len(epoch_losses) + 1), y_vals=epoch_losses,
                    title=model_name + "\n Epochs vs. Loss", x_label="Epochs", y_label="Loss", save_fp=save_fp_epochs)
    iteration_losses = train_dict["iteration_losses"]
    plot_utils.plot(x_vals=range(1, len(iteration_losses) + 1), y_vals=iteration_losses,
                     title=model_name + "\n Iterations vs. Loss", x_label="Iterations", y_label="Loss",
                     save_fp=save_fp_iterations)


def train(model, optimizer, lr_scheduler, dataloader, sub_batch_num, num_epochs, save_path, load_path):
    torch.backends.cudnn.benchmark = True
    scaler = torch.cuda.amp.GradScaler()
    model.train()
    model.cuda()
    if load_path is not None:
        epoch, model, optimizer, lr_scheduler, loss_dict = loadModel(model, optimizer, lr_scheduler, load_path)
    else:
        epoch = None
        loss_dict = {"epoch_losses": [], "iteration_losses": []}
    if epoch is None:
        epoch_min = 1
    else:
        epoch_min = epoch
    iteration_losses = []
    for epoch_num in range(epoch_min, num_epochs + 1):
        epoch_loss = 0.0
        for batch_num, data in enumerate(dataloader):
            if batch_num % 50 == 0 and batch_num != 0:
                print("Batch num " + str(batch_num))
            ims = data.to('cuda:0', non_blocking=True)
            N_ = ims.shape[0]
            N = int(N_/2)
            view_1 = ims[0:N]
            view_2 = ims[N:]
            with torch.cuda.amp.autocast():  # 16 bit precision = faster and less memory
                loss = model(view_1, view_2)
            loss.backward()
            loss = loss.item()
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)
            epoch_loss += loss
            iteration_losses.append(loss)
        if lr_scheduler is not None:
            lr_scheduler.step()
        loss_dict["epoch_losses"].extend([epoch_loss])
        loss_dict["iteration_losses"].extend(iteration_losses)
        print("\nFinished training epoch " + str(epoch_num) + " with average loss: " + str(round(epoch_loss/batch_num, 3)))
        saveModel(epoch_num, model, optimizer, lr_scheduler, loss_dict, save_path)
    return {"epoch_losses": loss_dict["epoch_losses"], "iteration_losses": loss_dict["iteration_losses"]}

if __name__ == "__main__":
    num_epochs = 20
    sub_batch_num = 1
    model_name = "Sim_Siam_Exp2"
    save_path = os.path.join(saved_models_path, model_name)
    load_path = os.path.join(saved_models_path, model_name)
    dataloader = dl.get_unlabeled_pair_dl(batch_size=64, num_workers=0, depth_only=True)
    rn_50 = rn.get_grayscale_rn50_backbone(pre_trained=True, with_pooling=True)
    rn_50.output_dim = 2048
    model = sim_siam.SimSiam(backbone=rn_50)


    optimizer = torch.optim.SGD(filter(lambda p: p.requires_grad, model.parameters()), lr=0.0125, momentum=0.9, weight_decay=0.0001)
    lr_scheduler = torch.optim.lr_scheduler.StepLR(optimizer, step_size=15, gamma=0.1)
    train_dict = train(model, optimizer, lr_scheduler, dataloader, sub_batch_num, num_epochs, save_path, load_path=None)
    plot_train_dict(train_dict, model_name, saved_plots_path)


    model = loadModel(model, None, None, save_path, model_only=True)
    visualize_filters.visualize_conv_filters_backbone(model)




