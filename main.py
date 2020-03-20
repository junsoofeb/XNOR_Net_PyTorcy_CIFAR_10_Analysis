#-*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import sys
import os
import torch
import argparse
import data
import util
import torch.nn as nn
import torch.optim as optim

from models import nin
from torch.autograd import Variable


def save_state(model, best_acc):
    print('==> Saving model ...')
    # 모델과 정확도 저장
    state = {
            'best_acc': best_acc,
            'state_dict': model.state_dict(),
            }
    for key in state['state_dict'].keys():
        if 'module' in key:
            state['state_dict'][key.replace('module.', '')] = \
                    state['state_dict'].pop(key)
    torch.save(state, 'models/nin.pth.tar')

def train(epoch):
    model.train()
    for batch_idx, (data, target) in enumerate(trainloader):
        # process the weights including binarization
        bin_op.binarization()
        
        # 순전파
        data, target = Variable(data.cuda()), Variable(target.cuda())
        optimizer.zero_grad()
        output = model(data)
        
        # 역전파
        loss = criterion(output, target)
        loss.backward()
        
        # 파라미터 저장
        bin_op.restore()
        bin_op.updateBinaryGradWeight()
        
        optimizer.step()
        if batch_idx % 100 == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}\tLR: {}'.format(
                epoch, batch_idx * len(data), len(trainloader.dataset),
                100. * batch_idx / len(trainloader), loss.data.item(),
                optimizer.param_groups[0]['lr']))
    return

def test():
    global best_acc
    model.eval()
    test_loss = 0
    correct = 0
    bin_op.binarization()
    for data, target in testloader:
        data, target = Variable(data.cuda()), Variable(target.cuda())
                                    
        output = model(data)
        test_loss += criterion(output, target).data.item()
        pred = output.data.max(1, keepdim=True)[1]
        correct += pred.eq(target.data.view_as(pred)).cpu().sum()
    bin_op.restore()
    acc = 100. * float(correct) / len(testloader.dataset)

    if acc > best_acc:
        best_acc = acc
        save_state(model, best_acc)
    
    test_loss /= len(testloader.dataset)
    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.2f}%)'.format(
        test_loss * 128., correct, len(testloader.dataset),
        100. * float(correct) / len(testloader.dataset)))
    print('Best Accuracy: {:.2f}%\n'.format(best_acc))
    return

def adjust_learning_rate(optimizer, epoch):
    update_list = [120, 200, 240, 280]
    if epoch in update_list:
        for param_group in optimizer.param_groups:
            param_group['lr'] = param_group['lr'] * 0.1
    return







if __name__=='__main__':
    # 옵션 주는 부분
    parser = argparse.ArgumentParser()
    parser.add_argument('--cpu', action='store_true',
            help='set if only CPU is available')
    parser.add_argument('--data', action='store', default='./data/',
            help='dataset path')
    parser.add_argument('--arch', action='store', default='nin',
            help='the architecture for the network: nin')
    parser.add_argument('--lr', action='store', default='0.01',
            help='the intial learning rate')
    parser.add_argument('--pretrained', action='store', default=None,
            help='the path to the pretrained model')
    parser.add_argument('--evaluate', action='store_true',
            help='evaluate the model')
    args = parser.parse_args()
    print('==> Options:',args)

    # 랜덤 값으로 채워진 텐서 생성을 위해 seed 설정
    torch.manual_seed(1)
    torch.cuda.manual_seed(1)

    # 데이터 경로 확인
    if not os.path.isfile(args.data+'/train_data'):
        # check the data path
        raise Exception\
                ('Please assign the correct data path with --data <DATA_PATH>')

    # data.py의 dataset클래스 생성
    trainset = data.dataset(root=args.data, train=True)
    # torch.utils.data.DataLoader는 불러온 data를 네트워크 입력으로 사용하기 위해 사전에 정리를 해주는 느낌
    trainloader = torch.utils.data.DataLoader(trainset, batch_size=128,
            shuffle=True, num_workers=2)

    # data.py의 dataset클래스 생성
    testset = data.dataset(root=args.data, train=False)
    # torch.utils.data.DataLoader는 불러온 data를 네트워크 입력으로 사용하기 위해 사전에 정리를 해주는 느낌
    testloader = torch.utils.data.DataLoader(testset, batch_size=100,
            shuffle=False, num_workers=2)

    # 클래스 정의
    classes = ('plane', 'car', 'bird', 'cat', 'deer', 'dog', 'frog', 'horse', 'ship', 'truck')

    # 모델 출력
    print('==> building model',args.arch,'...')
    
    # 옵션의 arch (architecture) 확인하고 nin아니면 에러
    if args.arch == 'nin':
        model = nin.Net()
    else:
        raise Exception(args.arch+' is currently not supported')

    # 옵션에 pretrained model을 사용하지 않을 경우
    if not args.pretrained:
        print('==> Initializing model parameters ...')
        best_acc = 0
        for m in model.modules():
            if isinstance(m, nn.Conv2d):
                m.weight.data.normal_(0, 0.05)
                m.bias.data.zero_()
                
    # 옵션에 pretrained model을 사용하는 경우
    else:
        print('==> Load pretrained model form', args.pretrained, '...')
        # cpu만 사용가능한 상황에 적용하기 위해서 예외처리
        try:
            pretrained_model = torch.load(args.pretrained)
        except:
            pretrained_model = torch.load(args.pretrained, map_location = 'cpu')
        finally:
            best_acc = pretrained_model['best_acc']
            model.load_state_dict(pretrained_model['state_dict'])

    # 옵션에 cpu 없는 경우
    if not args.cpu:
        model.cuda()
        model = torch.nn.DataParallel(model, device_ids=range(torch.cuda.device_count()))
    
    print(model)


    # learning rate, optimizer등 설정
    base_lr = float(args.lr)
    param_dict = dict(model.named_parameters())
    params = []

    for key, value in param_dict.items():
        params += [{'params':[value], 'lr': base_lr,
            'weight_decay':0.00001}]

    optimizer = optim.Adam(params, lr=0.10,weight_decay=0.00001)
    criterion = nn.CrossEntropyLoss()


    # util.py의 BinOp 클래스 생성 BinOp == binarization operator
    bin_op = util.BinOp(model)

    # 옵션에 evaluate 준 경우
    if args.evaluate:
        test()
        exit(0)

    # 학습 시작하는 부분
    for epoch in range(1, 320):
        adjust_learning_rate(optimizer, epoch)
        train(epoch)
        test()
