"""
Manual Topology Experiment with Background Traffic

"""
from __future__ import print_function
import settings
# from core.ns3.NS3Config import TopologyNetBT
from core.ns3.NS3Config import BackgroundTrafficConfig
from core.ns3.Topology import ComplexNet
from experiments import experiment_factory
from core.configure import gen_anomaly_dot
import ns3

ManualTopoExperiment = experiment_factory('ManualTopoExperiment', BaseClass)
from util import Namespace

zeros = lambda s:[[0 for i in xrange(s[1])] for j in xrange(s[0])]
def get_inet_adj_mat(fname):
    """ get the adjacent matrix from the topology.inet file.
    """
    fid = open(fname, 'r')
    i = -1
    while True:
        i += 1
        line = fid.readline()
        if not line: break
        if i == 0:
            totnode, totlink = [int(s.strip()) for s in line.rsplit()]
            adj_mat = zeros([totnode, totnode])
            continue
        if i <= totnode: # ignore the position information
            continue

        _from, _to, _lineBuffer = [s.strip() for s in line.rsplit()]
        adj_mat[int(_from)][int(_to)] = 1
    fid.close()

    return adj_mat

import pprint
import os
def fix_fs_addr_prefix_bug(f_name):
    """A fs node can either represent a real node or a network. If the addr in
    node's ipdests is add prefix, then fs will automatically consider it as network.
    However, the net_settings generated by Imalse GUI topology also use CIDR format.
    To reduce ambiguity, delete all network length information in **link_to_ip_map**
    """
    s = {}
    execfile(f_name, s)
    new_link_to_ip_map = {}
    for k, v in s.get('link_to_ip_map', {}).iteritems():
        new_link_to_ip_map[k] = [val.rsplit('/')[0] for val in v]
    s['link_to_ip_map'] = new_link_to_ip_map
    new_f_name = os.path.dirname(f_name) + '/new_' + os.path.basename(f_name)
    fid = open(new_f_name, 'w')
    fid.close()
    fid = open(new_f_name, 'a')
    for k, v in s.iteritems():
        if k.startswith('__'):
            continue
        fid.write('%s = '%(k))
        pprint.pprint(v, stream=fid)
    fid.close()
    return new_f_name

class ManualTopoBTExperiment(ManualTopoExperiment):
    """This is a extension of manual topology experiment which add background traffic
    to the network. """
    # routing protocol list, 'type':priority
    routing_helper_list = {
            'static':0,
            'nix':5,
            # 'olsr':10,
            }

    def initparser(self, parser):
        ManualTopoExperiment.initparser(self, parser)

        parser.set_defaults(back_traf="net_config/back_traf.py",
                )
        parser.add_option('--back_traf', dest="back_traf",
                help='confgiuration files for back ground traffic',
                )
        parser.add_option('--dot_file', default='net_config/ManualTopoBTConf.dot',
                help='the configured dot file')



    def load_para(self, f_name, encap=None, **kwargs):
        """load parameters.

        - **kwargs** contains some additional parameters
        - **encap** is the additional operation done to the data, for example,
            the default value encap=Namespace is to change parameters from dict
            to Namespace class.
        """
        s = kwargs
        execfile(f_name, s)
        return s if encap is None else encap(s)

    def get_config_net_desc(self):
        """ get the network description parameters

        It will load the network_settings file and

        - the new format of net_settings for Imalse and fs configure module
          are quite different. need to transform the net settigns parameters

        # transform the net settings format file to fs configure format
        # since the function of the generated dot file is just to provide behaviour
        # of models.
        # we don't need topology in the dot file to be exactly the same.
        # we just need the ip address for each interface.

        """
        # topo = get_inet_adj_mat(settings.ROOT + '/' + self.options.topology_file)
        # new_net_settings_file = fix_fs_addr_prefix_bug(settings.ROOT + '/' + self.options.net_settings)
        new_net_settings_file = settings.ROOT + '/' + self.options.net_settings
        net_desc= self.load_para(f_name=new_net_settings_file, encap=None)
        net_desc['node_type'] = 'NNode'
        net_desc['node_para'] = {}

        net_desc['link_to_ip_map'] = {}
        for type_, desc in net_desc['nets'].iteritems():
            if type_ == 'PointToPoint':
                net_desc['link_to_ip_map'].update(desc['IpMap'])
            elif type_ == "Csma":
                for nodes, ips in desc['IpMap'].iteritems():
                    for i in xrange(len(nodes) - 1):
                        net_desc['link_to_ip_map'].update({ (nodes[i], nodes[i+1]):(ips[i], ips[i+1]) })

        pairs = net_desc['link_to_ip_map'].keys()
        g_size = max(max(pairs)) + 1
        topo = zeros((g_size, g_size))
        for x, y in pairs:
            topo[x][y] = 1
        net_desc['topo'] = topo

        return net_desc

    def load_exper_settings(self, ns):
        from util import CIDR_to_subnet_mask
        # botnet related configuration
        self.server_id_set = ns['server_id_set']
        self.botmaster_id_set = ns['botmaster_id_set']
        self.client_id_set = ns['client_id_set']
        # print('ns.server_addr', ns.server_addr)

        # parse the server address
        if len(ns['server_addr']) == 0:
            self.SERVER_ADDR = ''
            self.NETWORK_BASE = ''
            self.IP_MASK = ''
        else:
            self.SERVER_ADDR, self.NETWORK_BASE, self.IP_MASK = CIDR_to_subnet_mask(ns['server_addr'][0]);


    @staticmethod
    def get_trace_config(net_settings):
        """transform net_setting to trace config
        """
        # TODO generate netDesc, normalDesc
        keys = ['pcap_links', 'pcap_nodes',
                'server_id_set', 'botmaster_id_set', 'client_id_set',
                'server_addr']
        ns = dict.copy(net_settings)
        return dict(elem for elem in ns.items() if elem[0] in keys)

    # @staticmethod
    def gen_back_traf_dot(self, net_settings):
        """generate background traffic dot file
        """

        # get back_traf parameter
        back_traf = self.load_para(
                f_name = settings.ROOT + '/' + self.options.back_traf,
                sim_t = self.options.simtime,
                )

        # call the SADIT/Configure module to generate the dot file specifying the background
        # traffic pattern.
        dot_file = settings.ROOT + '/' + self.options.dot_file
        gen_anomaly_dot(
                back_traf['ANO_LIST'],
                self.get_config_net_desc(),
                back_traf['NORM_DESC'],
                # self.options.dot_file
                dot_file
                )
        # return self.options.dot_file, self.get_trace_config(net_settings)
        return dot_file, self.get_trace_config(net_settings)

    def setup(self):
        BaseClass.setup(self)
        # net_settings = self.load_net_settings()
        net_settings = self.load_para(
                f_name = settings.ROOT + '/' + self.options.net_settings,
                )
        self.load_exper_settings(net_settings)

        # Generate dot file that describe the background traffic.
        dot_file, trace_config = self.gen_back_traf_dot(net_settings)

        ns3.LogComponentEnable("OnOffApplication", ns3.LOG_LEVEL_INFO)
        # self.net = TopologyNetBT(dot_file, trace_config,
                # routing_helper_list = self.routing_helper_list)
        self.net = ComplexNet(
                # os.path.abspath(self.options.topology_file),
                settings.ROOT + '/' + self.options.topology_file,
                self.options.topology_type,
                self.NodeCreator,
                net_settings,
                )

        bg_cofig = BackgroundTrafficConfig(dot_file, self.net)
        bg_cofig.config_onoff_app()

        self.net.set_trace()
        self._install_cmds(srv_addr = self.SERVER_ADDR)
        self.print_srv_addr()
        self._set_server_info()
        self.start_nodes()

