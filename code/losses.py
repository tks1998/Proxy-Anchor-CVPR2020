import torch
import torch.nn as nn
import torch.nn.functional as F
import math
import random
from pytorch_metric_learning import miners, losses

def binarize(T, nb_classes):
    T = T.cpu().numpy()
    import sklearn.preprocessing
    T = sklearn.preprocessing.label_binarize(
        T, classes = range(0, nb_classes)
    )
    T = torch.FloatTensor(T).cuda()
    return T

def l2_norm(input):
    input_size = input.size()
    buffer = torch.pow(input, 2)
    normp = torch.sum(buffer, 1).add_(1e-12)
    norm = torch.sqrt(normp)
    _output = torch.div(input, norm.view(-1, 1).expand_as(input))
    output = _output.view(input_size)
    return output

class Proxy_Anchor(torch.nn.Module):
    def __init__(self, nb_classes, sz_embed, mrg = 0.1, alpha = 32):
        torch.nn.Module.__init__(self)
        # Proxy Anchor Initialization
        self.proxies = torch.nn.Parameter(torch.randn(nb_classes, sz_embed).cuda())
        nn.init.kaiming_normal_(self.proxies, mode='fan_out')

        self.nb_classes = nb_classes
        self.sz_embed = sz_embed
        self.mrg = mrg
        self.alpha = alpha
        
    def forward(self, X, T):
        P = self.proxies

        cos = F.linear(l2_norm(X), l2_norm(P))  # Calcluate cosine similarity
        P_one_hot = binarize(T = T, nb_classes = self.nb_classes)
        N_one_hot = 1 - P_one_hot
    
        pos_exp = torch.exp(-self.alpha * (cos - self.mrg))
        neg_exp = torch.exp(self.alpha * (cos + self.mrg))

        with_pos_proxies = torch.nonzero(P_one_hot.sum(dim = 0) != 0).squeeze(dim = 1)   # The set of positive proxies of data in the batch
        num_valid_proxies = len(with_pos_proxies)   # The number of positive proxies
        
        P_sim_sum = torch.where(P_one_hot == 1, pos_exp, torch.zeros_like(pos_exp)).sum(dim=0) 
        N_sim_sum = torch.where(N_one_hot == 1, neg_exp, torch.zeros_like(neg_exp)).sum(dim=0)
        
        pos_term = torch.log(1 + P_sim_sum).sum() / num_valid_proxies
        neg_term = torch.log(1 + N_sim_sum).sum() / self.nb_classes
        loss = pos_term + neg_term     
        
        return loss


class AdaptiveProxyAnchorLoss(torch.nn.Module):
    def __init__(self, nb_classes, sz_embed, mrg=0.1, alpha=32, nb_proxies=1,scale_margin=10):
        torch.nn.Module.__init__(self)
        # Proxy Anchor Initialization
        self.nb_classes = nb_classes
        self.sz_embed = sz_embed
        self.mrg = torch.nn.Parameter(torch.tensor([mrg] * nb_classes, requires_grad=True, device='cuda',
                                                   dtype=torch.double))  # -> mrg -> list[...nb_classes]
        self.alpha = alpha
        self.nb_proxies = nb_proxies
        self.proxies_list = []
        self.scale_margin = scale_margin
        for i in range(self.nb_proxies):
            self.proxies = torch.nn.Parameter(torch.randn(nb_classes, sz_embed).cuda())
            nn.init.kaiming_normal_(self.proxies, mode='fan_out')
            self.proxies_list.append(self.proxies)

    def forward(self, X, T):
        P = self.proxies_list

        cos_list = [F.linear(l2_norm(X), l2_norm(P[i])) for i in range(self.nb_proxies)]

        tensor_sum_cos = torch.stack([i for i in cos_list])
        _data_cos = torch.mean(tensor_sum_cos, dim=0)

        P_one_hot = binarize(T=T, nb_classes=self.nb_classes)
        N_one_hot = 1 - P_one_hot

        pos_exp = torch.exp(-self.alpha * (_data_cos - self.mrg))
        neg_exp = torch.exp(self.alpha * (_data_cos + self.mrg))

        with_pos_proxies = torch.nonzero(P_one_hot.sum(dim=0) != 0).squeeze(
            dim=1)  # The set of positive proxies of data in the batch
        num_valid_proxies = len(with_pos_proxies)  # The number of positive proxies

        P_sim_sum = torch.where(P_one_hot == 1, pos_exp, torch.zeros_like(pos_exp)).sum(dim=0)
        N_sim_sum = torch.where(N_one_hot == 1, neg_exp, torch.zeros_like(neg_exp)).sum(dim=0)

        pos_term = torch.log(1 + P_sim_sum).sum() / num_valid_proxies
        neg_term = torch.log(1 + N_sim_sum).sum() / self.nb_classes

        loss = pos_term + neg_term + self.scale_margin*1/(torch.mean(self.mrg))
        return loss

class AdaptiveProxyAnchorLossAutoscale(torch.nn.Module):
    def __init__(self, nb_classes, sz_embed, mrg=0.1, alpha=32, nb_proxies=1,scale_margin=10):
        torch.nn.Module.__init__(self)
        # Proxy Anchor Initialization
        self.nb_classes = nb_classes
        self.sz_embed = sz_embed
        self.mrg = torch.nn.Parameter(torch.tensor([mrg] * nb_classes, requires_grad=True, device='cuda',
                                                   dtype=torch.double))  # -> mrg -> list[...nb_classes]
        self.alpha = alpha
        self.nb_proxies = nb_proxies
        self.proxies_list = []
        self.scale_margin = scale_margin
        for i in range(self.nb_proxies):
            self.proxies = torch.nn.Parameter(torch.randn(nb_classes, sz_embed).cuda())
            nn.init.kaiming_normal_(self.proxies, mode='fan_out')
            self.proxies_list.append(self.proxies)

    def forward(self, X, T):
        P = self.proxies_list

        cos_list = [F.linear(l2_norm(X), l2_norm(P[i])) for i in range(self.nb_proxies)]

        tensor_sum_cos = torch.stack([i for i in cos_list])
        _data_cos = torch.mean(tensor_sum_cos, dim=0)

        P_one_hot = binarize(T=T, nb_classes=self.nb_classes)
        N_one_hot = 1 - P_one_hot

        pos_exp = torch.exp(-self.alpha * (_data_cos - self.mrg))
        neg_exp = torch.exp(self.alpha * (_data_cos + self.mrg))

        with_pos_proxies = torch.nonzero(P_one_hot.sum(dim=0) != 0).squeeze(
            dim=1)  # The set of positive proxies of data in the batch
        num_valid_proxies = len(with_pos_proxies)  # The number of positive proxies

        P_sim_sum = torch.where(P_one_hot == 1, pos_exp, torch.zeros_like(pos_exp)).sum(dim=0)
        N_sim_sum = torch.where(N_one_hot == 1, neg_exp, torch.zeros_like(neg_exp)).sum(dim=0)

        pos_term = torch.log(1 + P_sim_sum).sum() / num_valid_proxies
        neg_term = torch.log(1 + N_sim_sum).sum() / self.nb_classes

        loss = pos_term + neg_term - self.scale_margin*(torch.mean(self.mrg))*(torch.abs(pos_term-neg_term))
        return loss


class ProxyAnchor_Newton(torch.nn.Module):
    def __init__(self, nb_classes, sz_embed, mrg=0.1, alpha=32):
        torch.nn.Module.__init__(self)
        # Proxy Anchor Initialization
        self.proxies = torch.nn.Parameter(torch.randn(nb_classes, sz_embed).cuda())
        nn.init.kaiming_normal_(self.proxies, mode='fan_out')

        self.nb_classes = nb_classes
        self.sz_embed = sz_embed
        self.mrg = mrg
        self.alpha = alpha

    def sim_matrix(a, b, eps=1e-8):
        """ added eps for numerical stability"""
        a_n, b_n = torch.norm(a,dim=1)[:, None], torch.norm(b,dim=1)[:, None]
        a_norm = a / torch.max(a_n, eps * torch.ones_like(a_n))
        b_norm = b / torch.max(b_n, eps * torch.ones_like(b_n))
        sim_mt = torch.mm(a_norm, b_norm.transpose(0, 1))
        return sim_mt

    def forward(self, X, T):
        P = self.proxies

        cos = F.linear(l2_norm(X), l2_norm(P))  # Calcluate cosine similarity
        new_ton_cos_list = torch.norm(X,dim=1)*torch.norm(P,dim=1).reshape(-1,1) / self.sim_matrix(X, P)
        mean_new_ton = torch.mean(new_ton_cos_list, dim=1)
        print(mean_new_ton)
        P_one_hot = binarize(T=T, nb_classes=self.nb_classes)
        N_one_hot = 1 - P_one_hot

        pos_exp = torch.exp(-self.alpha * (cos - mean_new_ton))
        neg_exp = torch.exp(self.alpha * (cos + mean_new_ton))

        with_pos_proxies = torch.nonzero(P_one_hot.sum(dim=0) != 0).squeeze(
            dim=1)  # The set of positive proxies of data in the batch
        num_valid_proxies = len(with_pos_proxies)  # The number of positive proxies

        P_sim_sum = torch.where(P_one_hot == 1, pos_exp, torch.zeros_like(pos_exp)).sum(dim=0)
        N_sim_sum = torch.where(N_one_hot == 1, neg_exp, torch.zeros_like(neg_exp)).sum(dim=0)

        pos_term = torch.log(1 + P_sim_sum).sum() / num_valid_proxies
        neg_term = torch.log(1 + N_sim_sum).sum() / self.nb_classes
        loss = pos_term + neg_term

        return loss

#
# class ProxyAnchor_Newton(torch.nn.Module):
#     def __init__(self, nb_classes, sz_embed, alpha=32, nb_proxies=1,scale_margin=10):
#         torch.nn.Module.__init__(self)
#         # Proxy Anchor Initialization
#         self.nb_classes = nb_classes
#         self.sz_embed = sz_embed
#         # self.mrg = torch.nn.Parameter(torch.tensor([mrg] * nb_classes, requires_grad=True, device='cuda',
#         #                                            dtype=torch.double))  # -> mrg -> list[...nb_classes]
#         self.alpha = alpha
#         self.nb_proxies = nb_proxies
#         self.proxies_list = []
#         self.scale_margin = scale_margin
#         for i in range(self.nb_proxies):
#             self.proxies = torch.nn.Parameter(torch.randn(nb_classes, sz_embed).cuda())
#             nn.init.kaiming_normal_(self.proxies, mode='fan_out')
#             self.proxies_list.(self.proxies)
#         self.proxies_list = torch.Tensor(self.proxies_list)
#     def sim_matrix(a, b, eps=1e-8):
#         """
#         added eps for numerical stability
#         """
#         a_n, b_n = a.norm(dim=1)[:, None], b.norm(dim=1)[:, None]
#         a_norm = a / torch.max(a_n, eps * torch.ones_like(a_n))
#         b_norm = b / torch.max(b_n, eps * torch.ones_like(b_n))
#         sim_mt = torch.mm(a_norm, b_norm.transpose(0, 1))
#         return sim_mt
#
#     def forward(self, X, T):
#         P = self.proxies_list
#
#         cos_list = [F.linear(l2_norm(X), l2_norm(P[i])) for i in range(self.nb_proxies)]
#         new_ton_cos_list = [F.linear(X, P[i])/self.sim_matrix(X,P[i]) for i in range(self.nb_proxies)]
#
#         tensor_sum_cos = torch.stack([i for i in cos_list])
#         margin = torch.stack([i for i in new_ton_cos_list])
#         _data_cos = torch.mean(tensor_sum_cos, dim=0)
#         margin_mean = torch.stack([i for i in new_ton_cos_list])
#         print(margin_mean)
#         P_one_hot = binarize(T=T, nb_classes=self.nb_classes)
#         N_one_hot = 1 - P_one_hot
#
#         pos_exp = torch.exp(-self.alpha * (_data_cos - margin_mean))
#         neg_exp = torch.exp(self.alpha * (_data_cos + margin_mean))
#
#         with_pos_proxies = torch.nonzero(P_one_hot.sum(dim=0) != 0).squeeze(
#             dim=1)  # The set of positive proxies of data in the batch
#         num_valid_proxies = len(with_pos_proxies)  # The number of positive proxies
#
#         P_sim_sum = torch.where(P_one_hot == 1, pos_exp, torch.zeros_like(pos_exp)).sum(dim=0)
#         N_sim_sum = torch.where(N_one_hot == 1, neg_exp, torch.zeros_like(neg_exp)).sum(dim=0)
#
#         pos_term = torch.log(1 + P_sim_sum).sum() / num_valid_proxies
#         neg_term = torch.log(1 + N_sim_sum).sum() / self.nb_classes
#
#         loss = pos_term + neg_term
#         return loss

# We use PyTorch Metric Learning library for the following codes.
# Please refer to "https://github.com/KevinMusgrave/pytorch-metric-learning" for details.
class Proxy_NCA(torch.nn.Module):
    def __init__(self, nb_classes, sz_embed, scale=32):
        super(Proxy_NCA, self).__init__()
        self.nb_classes = nb_classes
        self.sz_embed = sz_embed
        self.scale = scale
        self.loss_func = losses.ProxyNCALoss(num_classes = self.nb_classes, embedding_size = self.sz_embed, softmax_scale = self.scale).cuda()

    def forward(self, embeddings, labels):
        loss = self.loss_func(embeddings, labels)
        return loss
    
class MultiSimilarityLoss(torch.nn.Module):
    def __init__(self, ):
        super(MultiSimilarityLoss, self).__init__()
        self.thresh = 0.5
        self.epsilon = 0.1
        self.scale_pos = 2
        self.scale_neg = 50
        
        self.miner = miners.MultiSimilarityMiner(epsilon=self.epsilon)
        self.loss_func = losses.MultiSimilarityLoss(self.scale_pos, self.scale_neg, self.thresh)
        
    def forward(self, embeddings, labels):
        hard_pairs = self.miner(embeddings, labels)
        loss = self.loss_func(embeddings, labels, hard_pairs)
        return loss
    
class ContrastiveLoss(nn.Module):
    def __init__(self, margin=0.5, **kwargs):
        super(ContrastiveLoss, self).__init__()
        self.margin = margin
        self.loss_func = losses.ContrastiveLoss(neg_margin=self.margin) 
        
    def forward(self, embeddings, labels):
        loss = self.loss_func(embeddings, labels)
        return loss
    
class TripletLoss(nn.Module):
    def __init__(self, margin=0.1, **kwargs):
        super(TripletLoss, self).__init__()
        self.margin = margin
        self.miner = miners.TripletMarginMiner(margin, type_of_triplets = 'semihard')
        self.loss_func = losses.TripletMarginLoss(margin = self.margin)
        
    def forward(self, embeddings, labels):
        hard_pairs = self.miner(embeddings, labels)
        loss = self.loss_func(embeddings, labels, hard_pairs)
        return loss
    
class NPairLoss(nn.Module):
    def __init__(self, l2_reg=0):
        super(NPairLoss, self).__init__()
        self.l2_reg = l2_reg
        self.loss_func = losses.NPairsLoss(l2_reg_weight=self.l2_reg, normalize_embeddings = False)
        
    def forward(self, embeddings, labels):
        loss = self.loss_func(embeddings, labels)
        return loss