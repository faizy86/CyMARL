import numpy as np
import torch

class DRU:
	def __init__(self, sigma, device, comm_narrow=True, hard=False):
		self.sigma = sigma
		self.comm_narrow = comm_narrow
		self.hard = hard
		self.device = device

	def regularize(self, m):	
		m_reg = m + torch.randn(m.size()).to(self.device) * self.sigma
		if self.comm_narrow:
			m_reg = torch.sigmoid(m_reg).to(self.device)
		else:
			m_reg = torch.softmax(m_reg, 0).to(self.device)
		return m_reg

	def discretize(self, m):
		if self.hard:
			if self.comm_narrow:
				return (m.gt(0.5).float() - 0.5).sign().float()
			else:
				m_ = torch.zeros_like(m).to(self.device)
				if m.dim() == 1:      
					_, idx = m.max(0)
					m_[idx] = 1.
				elif m.dim() == 2:      
					_, idx = m.max(1)
					for b in range(idx.size(0)):
						m_[b, idx[b]] = 1.
				else:
					raise ValueError('Wrong message shape: {}'.format(m.size()))
				return m_
		else:
			scale = 2 * 20
			if self.comm_narrow:
				return torch.sigmoid((m.gt(0.5).float() - 0.5) * scale).to(self.device)
			else:
				return torch.softmax(m * scale, -1).to(self.device)

	def forward(self, m, train_mode):
		if train_mode:
			return self.regularize(m)
		else:
			return self.discretize(m)
			
