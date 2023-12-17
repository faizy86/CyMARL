import random

from CybORG.Agents.SimpleAgents.BaseAgent import BaseAgent
from CybORG.Shared import Results
from CybORG.Simulator.Actions import PrivilegeEscalate, ExploitRemoteService, DiscoverRemoteSystems, Impact, \
    DiscoverNetworkServices, Deny, Sleep


class RedAvailabilityAgent(BaseAgent):
    # a red agent that meanders through scenario 1b
    def __init__(self):
        self.scanned_subnets = []
        self.scanned_ips = []
        self.exploited_ips = []
        self.escalated_hosts = []
        self.disrupted_hosts = []
        self.host_ip_map = {}
        self.last_host = None
        self.last_ip = None
        self.last_action = None

    def train(self, results: Results):
        """allows an agent to learn a policy"""
        pass

    def get_action(self, observation, action_space):
        """gets an action from the agent that should be performed based on the agent's internal state and provided observation and action space"""
        self._process_success(observation)

        session = list(action_space['session'].keys())[0]

        # start by scanning
        for subnet in action_space["subnet"]:
            if not action_space["subnet"][subnet] or subnet in self.scanned_subnets:
                continue
            self.scanned_subnets.append(subnet)
            self.last_action = "DiscoverRemoteSystems"
            return DiscoverRemoteSystems(subnet=subnet, agent='Red', session=session)
        # discover network services
        # act on ip addresses discovered in first subnet
        addresses = [i for i in action_space["ip_address"]]
        random.shuffle(addresses)
        for address in addresses:
            if not action_space["ip_address"][address] or address in self.scanned_ips:
                continue
            self.scanned_ips.append(address)
            self.last_action = "DiscoverNetworkServices"
            return DiscoverNetworkServices(ip_address=address, agent='Red', session=session)

        # Deny
        hostnames = [x for x in action_space['hostname'].keys()]
        random.shuffle(hostnames)
        for hostname in hostnames:
            # test if host is not known
            if not action_space["hostname"][hostname] or hostname == 'User0':
                continue
            # test if host is exploited
            if hostname in self.host_ip_map and self.host_ip_map[hostname] not in self.exploited_ips:
                continue
            # test if host already has DoS proc
            if hostname in self.disrupted_hosts:
                continue
            self.disrupted_hosts.append(hostname)
            self.last_host = hostname
            self.last_action = "Deny"
            return Deny(hostname=hostname, agent='Red', session=session)

        # priv esc on owned hosts
        for hostname in hostnames:
            # test if host is not known
            if not action_space["hostname"][hostname]:
                continue
            # test if host is already priv esc
            if hostname in self.escalated_hosts:
                continue
            # test if host is exploited
            if hostname in self.host_ip_map and self.host_ip_map[hostname] not in self.exploited_ips:
                continue
            self.escalated_hosts.append(hostname)
            self.last_host = hostname
            self.last_action = "PrivilegeEscalate"
            return PrivilegeEscalate(hostname=hostname, agent='Red', session=session)

        # access unexploited hosts
        for address in addresses:
            # test if output of observation matches expected output
            if not action_space["ip_address"][address] or address in self.exploited_ips:
                continue
            self.exploited_ips.append(address)
            self.last_ip = address
            self.last_action = "ExploitRemoteServices"
            return ExploitRemoteService(ip_address=address, agent='Red', session=session)
    
        return Sleep
        #raise NotImplementedError('Red Meander has run out of options!')



    def _process_success(self, observation):
        if self.last_ip is not None:
            if observation['success'] == True:
                self.host_ip_map[[value['System info']['Hostname'] for key, value in observation.items()
                                  if key != 'success' and 'System info' in value
                                  and 'Hostname' in value['System info']][0]] = self.last_ip
            else:
                self._process_failed_ip()
            self.last_ip = None
        if self.last_host is not None:
            if observation['success'] == False:
                if self.last_host in self.escalated_hosts and self.last_host != 'User0':
                    self.escalated_hosts.remove(self.last_host)
                if self.last_host in self.disrupted_hosts and self.last_host != 'User0':
                    self.disrupted_hosts.remove(self.last_host)
                if self.last_host in self.host_ip_map and self.host_ip_map[self.last_host] in self.exploited_ips:
                    self.exploited_ips.remove(self.host_ip_map[self.last_host])
            self.last_host = None

    def _process_failed_ip(self):
        self.exploited_ips.remove(self.last_ip)
        #self.disrupted_hosts.remove(self.last_host)
        hosts_of_type = lambda y: [x for x in self.escalated_hosts if y in x]
        if len(hosts_of_type('Op')) > 0:
            for host in hosts_of_type('Op'):
                self.escalated_hosts.remove(host)
                self.disrupted_hosts.remove(host)
                ip = self.host_ip_map[host]
                self.exploited_ips.remove(ip)
        elif len(hosts_of_type('Ent')) > 0:
            for host in hosts_of_type('Ent'):
                self.escalated_hosts.remove(host)
                self.disrupted_hosts.remove(host)
                ip = self.host_ip_map[host]
                self.exploited_ips.remove(ip)

    def end_episode(self):
        self.scanned_subnets = []
        self.scanned_ips = []
        self.exploited_ips = []
        self.escalated_hosts = []
        self.disrupted_hosts = []
        self.host_ip_map = {}
        self.last_host = None
        self.last_ip = None

    def set_initial_values(self, action_space, observation):
        pass
