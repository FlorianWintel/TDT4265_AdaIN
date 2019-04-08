import argparse
import torch
import os
from tqdm import tqdm
from PIL import Image

from tensorboardX import SummaryWriter
from torchvision import transforms
from torchvision.utils import save_image
import torch.utils.data as data

import net
from sampler import InfiniteSamplerWrapper

def train_transform():
    transform_list = [
        transforms.Resize(size=(512, 512)),
        transforms.RandomCrop(256),
        transforms.ToTensor()
    ]
    return transforms.Compose(transform_list)

class FlatFolderDataset(data.Dataset):
    def __init__(self, root, transform):
        super(FlatFolderDataset, self).__init__()
        self.root = root
        self.paths = os.listdir(self.root)
        self.transform = transform

    def __getitem__(self, index):
        path = self.paths[index]
        img = Image.open(os.path.join(self.root, path)).convert('RGB')
        img = self.transform(img)
        return img

    def __len__(self):
        return len(self.paths)

    def name(self):
        return 'FlatFolderDataset'

parser = argparse.ArgumentParser()
parser.add_argument('--data_dir', type=str, required=True,
                    help='Directory path to a batch of content images')
parser.add_argument('--enc', type=str, default='models/vgg_normalised.pth')
parser.add_argument('--dec', type=str, default='models/decoder.pth')
# Training
parser.add_argument('--log_dir', default='./logs',
                    help='Directory to save the log')
parser.add_argument('--save_dir', default='./experiments',
                    help='Directory to save the model')
parser.add_argument('--max_iter', type=int, default=1000)
parser.add_argument('--lr', type=float, default=1e-4)
parser.add_argument('--batch_size', type=int, default=8)
parser.add_argument('--n_threads', type=int, default=16)

# Testing
parser.add_argument('--test', type=bool, default=False)
parser.add_argument('--output', type=str, default='output',
                    help='Directory to save the output image(s)')
parser.add_argument('--save_ext', default='.jpg',
                    help='The extension name of the output image')
args = parser.parse_args()

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

dataset = FlatFolderDataset(args.data_dir, train_transform())

if args.test: 
    batch = 1
else:
    batch = args.batch_size
    
dataset_iter = iter(data.DataLoader(
    dataset, batch_size=batch,
    sampler=InfiniteSamplerWrapper(dataset),
    num_workers=args.n_threads))

# if we don't get the model we use vgg
if args.enc == 'models/vgg_normalised.pth':
    # define decoder and encoder
    encoder, decoder = net.vgg19(args.enc, args.test, args.dec)
else:
    if args.enc == 'models/resnet18-5c106cde.pth':
        # define decoder and encoder
        encoder, decoder = net.resnet18(args.enc, args.test, decoder=args.dec)
    else:
        # inception 3
        encoder, decoder = net.inception3(args.enc, args.test, decoder=args.dec)

if args.test:
    if not os.path.exists(args.output):
        os.mkdir(args.output)

    decoder.eval()
    encoder.eval()
    
    encoder.to(device)
    decoder.to(device)
    
    images = next(dataset_iter).to(device)
    with torch.no_grad():
        output = decoder(encoder(images))
        output = output.cpu()

    output_name = '{:s}/autoencoder_test{:s}'.format(args.output, args.save_ext)
    save_image(output, output_name)

else:
    if not os.path.exists(args.save_dir):
        os.mkdir(args.save_dir)
    if not os.path.exists(args.log_dir):
        os.mkdir(args.log_dir)
    writer = SummaryWriter(log_dir=args.log_dir)
    
    encoder.to(device)
    decoder.to(device)
    
    optimizer = torch.optim.Adam(decoder.parameters(), lr=args.lr)

    for i in tqdm(range(args.max_iter)):
        images = next(dataset_iter).to(device)
        output = decoder(encoder(images))
        loss = torch.dist(output,images)
        
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    
        writer.add_scalar('loss', loss.item(), i + 1)
    state_dict = decoder.state_dict()
    for key in state_dict.keys():
        state_dict[key] = state_dict[key].to(torch.device('cpu'))
        torch.save(state_dict,
                   '{:s}/dec_auto.pth'.format(args.save_dir))
    writer.close()