import torch
import torch.nn.functional as F
from torch.nn import Linear
from torch_geometric.nn import GCNConv, global_mean_pool
import pdb
from KPGNN import KPGCNConv

class NestedGCN(torch.nn.Module):
    def __init__(self, dataset, num_layers, hidden, use_z=False, use_rd=False):
        super(NestedGCN, self).__init__()
        # print('dataset:',dataset.num_subgraphs)
        self.dataset = dataset
        self.use_rd = use_rd
        self.use_z = use_z
        if self.use_rd:
            self.rd_projection = torch.nn.Linear(1, 8)
        if self.use_z:
            self.z_embedding = torch.nn.Embedding(1000, 8)
        input_dim = dataset.num_features
        if self.use_z or self.use_rd:
            input_dim += 8

        self.conv1 = GCNConv(input_dim, hidden)
        self.convs = torch.nn.ModuleList()
        for i in range(num_layers - 1):
            self.convs.append(GCNConv(hidden, hidden))
        self.lin1 = torch.nn.Linear(num_layers * hidden, hidden)
        self.lin2 = Linear(hidden, dataset.num_classes)

    def reset_parameters(self):
        if self.use_rd:
            self.rd_projection.reset_parameters()
        if self.use_z:
            self.z_embedding.reset_parameters()
        self.conv1.reset_parameters()
        for conv in self.convs:
            conv.reset_parameters()
        self.lin1.reset_parameters()
        self.lin2.reset_parameters()

    def forward(self, data,return_features=False):
        x, edge_index, batch = data.x, data.edge_index, data.batch
        
        # node label embedding
        z_emb = 0
        if self.use_z and 'z' in data:
            ### computing input node embedding
            z_emb = self.z_embedding(data.z)
            if z_emb.ndim == 3:
                z_emb = z_emb.sum(dim=1)
        
        if self.use_rd and 'rd' in data:
            rd_proj = self.rd_projection(data.rd)
            z_emb += rd_proj

        if self.use_rd or self.use_z:
            x = torch.cat([z_emb, x], -1)

        x = F.relu(self.conv1(x, edge_index))
        xs = [x]
        
        # i=0
        # for conv in self.convs:
        #     i+=1
        #     x=conv(x, edge_index)
            
        #     if i==1:
        #         # Compute logits
        #         logits = self.fc(x)
        #         print('logits: ',logits.shape)

        #         # Compute class probabilities
        #         probs = F.softmax(logits, dim=1)
        #         print('probs: ',probs.shape)
        #         # cam = torch.matmul(x.unsqueeze(2), probs.unsqueeze(1)).squeeze()

                
            
        #     x = F.relu()
        #     xs += [x]
        
        for conv in self.convs:
            x = F.relu(conv(x, edge_index))
            xs += [x]
        x = global_mean_pool(torch.cat(xs, dim=1), data.node_to_subgraph)
        x = global_mean_pool(x, data.subgraph_to_graph)
        x = F.relu(self.lin1(x))
        x = F.dropout(x, p=0.5, training=self.training)
        features = self.lin2(x) # logits
        
        probs = F.softmax(features, dim=1)
        cam = torch.matmul(x.unsqueeze(2), probs.unsqueeze(1)) 
        # print('x.unsqueeze(2) : ',x.unsqueeze(2).shape)
        # print('probs.unsqueeze(1) : ',probs.unsqueeze(1).shape)
        # print('cam: ',cam)
        # cam = torch.matmul(x.squeeze(), probs)

        if return_features:
            return F.log_softmax(features, dim=-1),features,cam
        else:
            return F.log_softmax(features, dim=-1)

    def __repr__(self):
        return self.__class__.__name__

class NestedKPGCN(torch.nn.Module):
    def __init__(self, dataset, num_layers, hidden, use_z=False, use_rd=False):
        super(NestedKPGCN, self).__init__()
        print('NestedKPGCN')
        self.use_rd = use_rd
        self.use_z = use_z
        if self.use_rd:
            self.rd_projection = torch.nn.Linear(1, 8)
        if self.use_z:
            self.z_embedding = torch.nn.Embedding(1000, 8)
        input_dim = dataset.num_features
        if self.use_z or self.use_rd:
            input_dim += 8

        self.conv1=KPGCNConv(input_dim, hidden, K=2, num_hop1_edge=1, num_pe=1, combine="geometric")
        # self.conv1 = GCNConv(input_dim, hidden)
        self.convs = torch.nn.ModuleList()
        for i in range(num_layers - 1):
            self.convs.append(KPGCNConv(input_dim, hidden, K=2))
        self.lin1 = torch.nn.Linear(num_layers * hidden, hidden)
        self.lin2 = Linear(hidden, dataset.num_classes)

    def reset_parameters(self):
        if self.use_rd:
            self.rd_projection.reset_parameters()
        if self.use_z:
            self.z_embedding.reset_parameters()
        self.conv1.reset_parameters()
        for conv in self.convs:
            conv.reset_parameters()
        self.lin1.reset_parameters()
        self.lin2.reset_parameters()

    def forward(self, data):
        x, edge_index, batch ,edge_attr= data.x, data.edge_index, data.batch ,data.original_edge_attr
        print('kpgcn forward: ',data)
        # node label embedding
        z_emb = 0
        if self.use_z and 'z' in data:
            ### computing input node embedding
            z_emb = self.z_embedding(data.z)
            if z_emb.ndim == 3:
                z_emb = z_emb.sum(dim=1)
        
        if self.use_rd and 'rd' in data:
            rd_proj = self.rd_projection(data.rd)
            z_emb += rd_proj

        if self.use_rd or self.use_z:
            x = torch.cat([z_emb, x], -1)

        x = F.relu(self.conv1(x, edge_index,edge_attr))
        xs = [x]
        for conv in self.convs:
            x = F.relu(conv(x, edge_index,edge_attr))
            xs += [x]
        x = global_mean_pool(torch.cat(xs, dim=1), data.node_to_subgraph)
        x = global_mean_pool(x, data.subgraph_to_graph)
        x = F.relu(self.lin1(x))
        x = F.dropout(x, p=0.5, training=self.training)
        x = self.lin2(x)
        return F.log_softmax(x, dim=-1)

    def __repr__(self):
        return self.__class__.__name__



class GCN(torch.nn.Module):
    def __init__(self, dataset, num_layers, hidden, *args, **kwargs):
        super(GCN, self).__init__()
        self.conv1 = GCNConv(dataset.num_features, hidden)
        self.convs = torch.nn.ModuleList()
        for i in range(num_layers - 1):
            self.convs.append(GCNConv(hidden, hidden))
        self.lin1 = torch.nn.Linear(num_layers * hidden, hidden)
        self.lin2 = Linear(hidden, dataset.num_classes)

    def reset_parameters(self):
        self.conv1.reset_parameters()
        for conv in self.convs:
            conv.reset_parameters()
        self.lin1.reset_parameters()
        self.lin2.reset_parameters()

    def forward(self, data):
        x, edge_index, batch = data.x, data.edge_index, data.batch
        x = F.relu(self.conv1(x, edge_index))
        xs = [x]
        for conv in self.convs:
            x = F.relu(conv(x, edge_index))
            xs += [x]
        x = global_mean_pool(torch.cat(xs, dim=1), batch)
        x = F.relu(self.lin1(x))
        x = F.dropout(x, p=0.5, training=self.training)
        x = self.lin2(x)
        return F.log_softmax(x, dim=-1)

    def __repr__(self):
        return self.__class__.__name__
