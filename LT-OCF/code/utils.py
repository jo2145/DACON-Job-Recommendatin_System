import world
import torch
from torch import nn, optim
import numpy as np
from torch import log
from dataloader import BasicDataset
from time import time
from model import LightGCN
from model import PairWiseModel
from sklearn.metrics import roc_auc_score
import random
import os
try:
    from cppimport import imp_from_filepath
    from os.path import join, dirname
    path = join(dirname(__file__), "sources/sampling.cpp")
    sampling = imp_from_filepath(path)
    sampling.seed(world.seed)
    sample_ext = True
except:
    world.cprint("Cpp extension not loaded")
    sample_ext = False


class BPRLoss:
    def __init__(self,
                 recmodel : PairWiseModel,
                 config : dict):
        self.model = recmodel
        self.weight_decay = config['decay']
        self.lr = config['lr']
        self.opt = optim.Adam(recmodel.parameters(), lr=self.lr)

    def stageOne(self, users, pos, neg):
        loss, reg_loss = self.model.bpr_loss(users, pos, neg)
        reg_loss = reg_loss*self.weight_decay
        loss = loss + reg_loss

        self.opt.zero_grad()
        loss.backward()
        self.opt.step()

        return loss.cpu().item()

class BPRLossT_deprecated:
    def __init__(self,
                 recmodel : PairWiseModel,
                 config : dict):
        self.model = recmodel
        self.weight_decay = config['decay']
        self.lr = config['lr']
        self.lr_time = config['lr_time']
        self.opt = optim.Adam(recmodel.parameters(), lr=self.lr)
        self.all_time = self.model.get_time()
        self.opt_time = optim.Adam(self.all_time, lr=self.lr_time)

    def stageOne(self, users, pos, neg):
        loss, reg_loss = self.model.bpr_loss(users, pos, neg)
        reg_loss = reg_loss*self.weight_decay
        loss = loss + reg_loss

        self.opt.zero_grad()
        self.opt_time.zero_grad()
        loss.backward()
        self.opt.step()
        self.opt_time.step()

        return loss.cpu().item(), self.all_time

class BPRLossT:
    def __init__(self,
                 recmodel : PairWiseModel,
                 config : dict):
        self.model = recmodel
        self.weight_decay = config['decay']
        self.lr = config['lr']
        self.lr_time = config['lr_time']
        self.opt = optim.Adam(recmodel.parameters(), lr=self.lr)
        self.all_times  = recmodel.get_time()
        self.opt_times = optim.Adam(self.all_times, lr=self.lr_time)

    def stageOne(self, users, pos, neg):
        loss, reg_loss = self.model.bpr_loss(users, pos, neg)
        reg_loss = reg_loss*self.weight_decay
        loss = loss + reg_loss

        self.opt.zero_grad()
        self.opt_times.zero_grad()
        loss.backward()
        self.opt.step()
        self.opt_times.step()
        return loss.cpu().item(), self.all_times

def UniformSample_original(dataset, neg_ratio = 1):
    dataset : BasicDataset
    allPos = dataset.allPos
    start = time()
    if sample_ext:
        S = sampling.sample_negative(dataset.n_users, dataset.m_items,
                                     dataset.trainDataSize, allPos, neg_ratio)
    else:
        S = UniformSample_original_python(dataset)
    return S

def UniformSample_original_python(dataset):
    """
    the original impliment of BPR Sampling in LightGCN
    :return:
        np.array
    """
    total_start = time()
    dataset : BasicDataset
    user_num = dataset.trainDataSize
    users = np.random.randint(0, dataset.n_users, user_num)
    allPos = dataset.allPos
    S = []
    sample_time1 = 0.
    sample_time2 = 0.
    for i, user in enumerate(users):
        start = time()
        posForUser = allPos[user]
        if len(posForUser) == 0:
            continue
        sample_time2 += time() - start
        posindex = np.random.randint(0, len(posForUser))
        positem = posForUser[posindex]
        while True:
            negitem = np.random.randint(0, dataset.m_items)
            if negitem in posForUser:
                continue
            else:
                break
        S.append([user, positem, negitem])
        end = time()
        sample_time1 += end - start
    total = time() - total_start
    return np.array(S)

# ===================end samplers==========================
# =====================utils====================================

def set_seed(seed):
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    torch.manual_seed(seed)

def getFileName():
    if world.model_name == 'mf':
        file = f"mf-{world.dataset}-{world.config['latent_dim_rec']}.pth.tar"
    elif world.model_name == 'lgn':
        file = f"lgn-{world.dataset}-{world.config['lightGCN_n_layers']}-{world.config['latent_dim_rec']}.pth.tar"
    elif world.model_name == 'ltocf':
        file = f"ltocf-{world.dataset}-{world.config['solver']}-adjoint{world.adjoint}-learnable{world.config['learnable_time']}-dual{world.config['dual_res']}-lr{world.config['lr']}-lrt{world.config['lr_time']}-decay{world.config['decay']}-{world.comment}.pth.tar"
    elif world.model_name == 'ltocf2':
        file = f"ltocf2-{world.dataset}-{world.config['solver']}-adjoint{world.adjoint}-learnable{world.config['learnable_time']}-dual{world.config['dual_res']}-lr{world.config['lr']}-lrt{world.config['lr_time']}-decay{world.config['decay']}-{world.comment}.pth.tar"
    elif world.model_name == 'ltocf1':
        file = f"ltocf1-{world.dataset}-{world.config['solver']}-adjoint{world.adjoint}-learnable{world.config['learnable_time']}-dual{world.config['dual_res']}-lr{world.config['lr']}-lrt{world.config['lr_time']}-decay{world.config['decay']}-{world.comment}.pth.tar"    
    
    
    return os.path.join(world.FILE_PATH,file)

def getPretrainedFileName(pretrained_name):
    if world.model_name == 'ltocf':
        file = pretrained_name
    elif world.model_name == 'ltocf2':
        file = pretrained_name
    elif world.model_name == 'ltocf1':
        file = pretrained_name
    else:
        file = pretrained_name
    return os.path.join(world.PRETRAINED_FILE_PATH,file)

def minibatch(*tensors, **kwargs):

    batch_size = kwargs.get('batch_size', world.config['bpr_batch_size'])

    if len(tensors) == 1:
        tensor = tensors[0]
        for i in range(0, len(tensor), batch_size):
            yield tensor[i:i + batch_size]
    else:
        for i in range(0, len(tensors[0]), batch_size):
            yield tuple(x[i:i + batch_size] for x in tensors)


def shuffle(*arrays, **kwargs):

    require_indices = kwargs.get('indices', False)

    if len(set(len(x) for x in arrays)) != 1:
        raise ValueError('All inputs to shuffle must have '
                         'the same length.')

    shuffle_indices = np.arange(len(arrays[0]))
    np.random.shuffle(shuffle_indices)

    if len(arrays) == 1:
        result = arrays[0][shuffle_indices]
    else:
        result = tuple(x[shuffle_indices] for x in arrays)

    if require_indices:
        return result, shuffle_indices
    else:
        return result


class timer:
    """
    Time context manager for code block
        with timer():
            do something
        timer.get()
    """
    from time import time
    TAPE = [-1]  # global time record
    NAMED_TAPE = {}

    @staticmethod
    def get():
        if len(timer.TAPE) > 1:
            return timer.TAPE.pop()
        else:
            return -1

    @staticmethod
    def dict(select_keys=None):
        hint = "|"
        if select_keys is None:
            for key, value in timer.NAMED_TAPE.items():
                hint = hint + f"{key}:{value:.2f}|"
        else:
            for key in select_keys:
                value = timer.NAMED_TAPE[key]
                hint = hint + f"{key}:{value:.2f}|"
        return hint

    @staticmethod
    def zero(select_keys=None):
        if select_keys is None:
            for key, value in timer.NAMED_TAPE.items():
                timer.NAMED_TAPE[key] = 0
        else:
            for key in select_keys:
                timer.NAMED_TAPE[key] = 0

    def __init__(self, tape=None, **kwargs):
        if kwargs.get('name'):
            timer.NAMED_TAPE[kwargs['name']] = timer.NAMED_TAPE[
                kwargs['name']] if timer.NAMED_TAPE.get(kwargs['name']) else 0.
            self.named = kwargs['name']
            if kwargs.get("group"):
                # add group function
                pass
        else:
            self.named = False
            self.tape = tape or timer.TAPE

    def __enter__(self):
        self.start = timer.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.named:
            timer.NAMED_TAPE[self.named] += timer.time() - self.start
        else:
            self.tape.append(timer.time() - self.start)


# ====================Metrics==============================
# =========================================================
def RecallPrecision_ATk(test_data, r, k):
    """
    test_data should be a list? cause users may have different amount of pos items. shape (test_batch, k)
    pred_data : shape (test_batch, k) NOTE: pred_data should be pre-sorted
    k : top-k
    """
    right_pred = r[:, :k].sum(1)
    precis_n = k
    recall_n = np.array([len(test_data[i]) for i in range(len(test_data))])
    recall = np.sum(right_pred/recall_n)
    precis = np.sum(right_pred)/precis_n
    return {'recall': recall, 'precision': precis}


def MRRatK_r(r, k):
    """
    Mean Reciprocal Rank
    """
    pred_data = r[:, :k]
    scores = np.log2(1./np.arange(1, k+1))
    pred_data = pred_data/scores
    pred_data = pred_data.sum(1)
    return np.sum(pred_data)

def NDCGatK_r(test_data,r,k):
    """
    Normalized Discounted Cumulative Gain
    rel_i = 1 or 0, so 2^{rel_i} - 1 = 1 or 0
    """
    assert len(r) == len(test_data)
    pred_data = r[:, :k]

    test_matrix = np.zeros((len(pred_data), k))
    for i, items in enumerate(test_data):
        length = k if k <= len(items) else len(items)
        test_matrix[i, :length] = 1
    max_r = test_matrix
    idcg = np.sum(max_r * 1./np.log2(np.arange(2, k + 2)), axis=1)
    dcg = pred_data*(1./np.log2(np.arange(2, k + 2)))
    dcg = np.sum(dcg, axis=1)
    idcg[idcg == 0.] = 1.
    ndcg = dcg/idcg
    ndcg[np.isnan(ndcg)] = 0.
    return np.sum(ndcg)

def AUC(all_item_scores, dataset, test_data):
    """
        design for a single user
    """
    dataset : BasicDataset
    r_all = np.zeros((dataset.m_items, ))
    r_all[test_data] = 1
    r = r_all[all_item_scores >= 0]
    test_item_scores = all_item_scores[all_item_scores >= 0]
    return roc_auc_score(r, test_item_scores)

def getLabel(test_data, pred_data):
    r = []
    for i in range(len(test_data)):
        groundTrue = test_data[i]
        predictTopK = pred_data[i]
        pred = list(map(lambda x: x in groundTrue, predictTopK))
        pred = np.array(pred).astype("float")
        r.append(pred)
    return np.array(r).astype('float')

# ====================end Metrics=============================
# =========================================================
def save_rating_user(ratings, users, name="", epoch=0, recall=0):
    SAVE_PATH = "../results/"
    # rating 정보 저장
    file_path = f"{SAVE_PATH}rating{name}_{epoch:d}_{recall:.4f}.txt"
    if recall==0:
        file_path = f"{SAVE_PATH}rating{name}_{epoch:d}.txt"

    # 텐서를 텍스트 파일에 저장
    with open(file_path, "w") as file:
        for tensor in ratings:
            # 텐서를 문자열로 변환
            tensor = tensor.tolist()
            tensor_str = "\n".join([" ".join(map(str, row)) for row in tensor])
            file.write(tensor_str)
            file.write("\n")  # 텐서 간 구분을 위한 공백 줄 추가
            # 텍스트 파일 경로

    # user 정보 저장
    file_path = f"{SAVE_PATH}user{name}_{epoch:d}_{recall:.4f}.txt"
    if recall==0:
        file_path = f"{SAVE_PATH}user{name}_{epoch:d}.txt"

    # 텍스트 파일에 저장
    with open(file_path, "w") as file:
        for user_list in users:
            user_str = "\n".join(map(str, user_list))
            file.write(user_str)
            file.write("\n")  # 구분을 위한 공백 줄 추가

def save_proba(probas, name="", epoch=0, recall=0):
    SAVE_PATH = "../results/"

    # user 정보 저장
    file_path = f"{SAVE_PATH}proba{name}_{epoch:d}_{recall:.4f}.txt"
    if recall==0:
        file_path = f"{SAVE_PATH}proba{name}_{epoch:d}.txt"

    # 텍스트 파일에 저장
    with open(file_path, "w") as file:
        proba_str = "\n".join([" ".join(map(str, row)) for row in probas])
        file.write(proba_str)