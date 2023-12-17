import inspect
import os

import torch
from gym.spaces import flatdim
from envs.multiagentenv import MultiAgentEnv

from CybORG import CybORG
from CybORG.Shared.Scenarios.FileReaderScenarioGenerator import \
    FileReaderScenarioGenerator
from CybORG.Wrappers import FixedFlatWrapper
from CybORG.Wrappers import MultiAgentDIALWrapper, BlueTableDIALWrapper, EnumActionDIALWrapper, MultiAgentDIALTestWrapper, PettingZooParallelWrapper

class CyborgEnv(MultiAgentEnv):

    def __init__(self, map_name, time_limit=100, action_masking=False, wrapper_type='table', **kwargs):
        self.opt= None
        self.episode_limit = time_limit
        self.action_masking = action_masking
        self._env = self._create_env(map_name, time_limit, wrapper_type)
        
        self.n_agents = len(self._env.agents)
        self._agent_ids = list(self._env.agents)
        self._obs = None

        self.longest_action_space = max(self._env.action_spaces.values(), key=lambda x: x.n)
        self.longest_observation_space = max(
            self._env.observation_spaces.values(), key=lambda x: x.shape
        )
        self.longest_turn_vector_obs = flatdim(self.longest_observation_space) + time_limit
        self.step_count = 0
        self.sender = []

    def reset(self):
        # Returns initial observations and states
        self._obs = self._env.reset()
        self._obs = list(self._obs.values())
        self._elapsed_steps = 0
        self.step_count = 0

        return self.get_state()
    
    def step(self, actions):
        # Returns reward, terminated
        actions = actions - 1
        actions = actions.tolist()
        action_dict = dict(zip(self._agent_ids, actions))
        self._obs, reward, done, info = self._env.step(action_dict)
        self._obs = list(self._obs.values())
        self._update_sender()
        self.step_count += 1
        return torch.tensor(list(reward.values())), int(all(done.values()))

    def get_obs(self):
        # Returns all agent observations in a list
        return self._obs

    def get_obs_agent(self, agent_id):
        # Returns observation for agent_id
        return self._obs[agent_id]

    def get_obs_size(self):
        # Returns the shape of the observation 
        return flatdim(self.longest_observation_space)

    def get_state(self):
        
        if self.step_count < self.episode_limit:
            state = []
            turn_vector = [0] * (self.episode_limit)
            turn_vector[self.step_count] = 1 # Monitor the current timestep
            for agent in range(self.n_agents):
                agent_obs = self._obs[agent]
                flattened_obs = sum(agent_obs, [])  # Concatenate sublists
                padded_obs = flattened_obs + [-1] * (self.get_obs_size() - len(flattened_obs))
                padded_obs.extend(turn_vector)
                state.append(padded_obs)
            state_tensor = torch.tensor(state, dtype=torch.float)
            return state_tensor
        return torch.zeros(self.n_agents, self.longest_turn_vector_obs)

    def get_state_size(self):
        # Returns the shape of the state
        return self.n_agents * flatdim(self.longest_observation_space)

    def get_avail_actions(self):
        avail_actions = []
        for agent_id in range(self.n_agents):
            avail_agent = self.get_avail_agent_actions(agent_id)
            avail_actions.append(avail_agent)
        return avail_actions

    def get_avail_agent_actions(self, agent_id):
        # Returns the available actions for agent_id 
        agent_name = self._agent_ids[agent_id]
        if self.action_masking:
            action_dict = self._env.action_space(agent_name)
            valid = list(map(int, self._env.get_action_mask(agent=agent_name)))
        else:
            valid = flatdim(self._env.action_space(agent_name)) * [1]

        invalid = [0] * (self.longest_action_space.n - len(valid))
        return valid + invalid

    def get_total_actions(self):
        # Returns the total number of actions an agent could ever take 
        # TODO: This is only suitable for a discrete 1 dimensional action space for each agent
        return flatdim(self.longest_action_space)

    def render(self):
        self._env.render()

    def close(self):
        self._env.close()

    def seed(self):
        return self._env.seed

    def save_replay(self):
        pass

    def get_stats(self, steps):
        #TODO
        return 0
    
    def get_action_range(self, a_total, step, agent_id):

        action_dtype = torch.long
        action_range = torch.zeros((2), dtype=action_dtype)
        comm_range = torch.zeros((2), dtype=action_dtype)

        agent_name = self._agent_ids[agent_id]
        action_space = flatdim(self._env.action_space(agent_name))

        action_range = torch.tensor([1, action_space], dtype=action_dtype)
        comm_range = torch.tensor([self.get_total_actions() + 1, a_total], dtype=action_dtype)
        return action_range, comm_range

    def _update_sender(self):
        sender = []
        for agent in range(self.n_agents):
            agent_obs = self.get_obs_agent(agent)
            value = 0
            for i, host in enumerate(agent_obs):
                if host[1] == 1:
                    value = 1
            sender.append(value)
        self.sender.append(sender)

    def get_comm_limited(self, comm_limited, step, agent_id):
        if comm_limited:
            comm_lim = {}
            agent_messages = []
            if step > 0:
                agent_messages = self.sender[step - 1]
                for i in range(len(agent_messages)):
                    if i != agent_id:
                        comm_lim[i] = agent_messages[i]
            print(comm_lim)
            return comm_lim
        return None
    
    def get_env_info(self):
        env_info = {"obs_shape": self.longest_turn_vector_obs,
                    "n_actions": self.get_total_actions(),
                    "n_agents": self.n_agents,
                    "episode_limit": self.episode_limit}
        return env_info
    
    def _wrap_env(self, env, wrapper_type):
        if wrapper_type == 'table':
            return MultiAgentDIALWrapper(BlueTableDIALWrapper(EnumActionDIALWrapper(env), output_mode='vector'))
        elif wrapper_type == 'test':
            return MultiAgentDIALTestWrapper(EnumActionDIALWrapper(env))
        elif wrapper_type == 'pz':
            return PettingZooParallelWrapper(env=env)
        else:
            return MultiAgentDIALWrapper(FixedFlatWrapper(EnumActionDIALWrapper(env)))
        

    def _create_env(self, map_name, time_limit, wrapper_type):
        # Get the directory containing cyborg
        cyborg_dir = os.path.dirname(os.path.dirname(inspect.getfile(CybORG)))
        path = cyborg_dir + f'/CybORG/Shared/Scenarios/scenario_files/{map_name}.yaml'
        norm_path = os.path.normpath(path)

        # Make scenario from specified file
        sg = FileReaderScenarioGenerator(norm_path)
        cyborg = CybORG(scenario_generator=sg, time_limit=time_limit)
        env = self._wrap_env(cyborg, wrapper_type)
        return env
    