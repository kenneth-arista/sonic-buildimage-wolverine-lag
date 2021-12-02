import os
import signal
import sys
import syslog
import traceback

from swsscommon import swsscommon

from .config import ConfigMgr
from .directory import Directory
from .log import log_notice, log_crit
from .managers_allow_list import BGPAllowListMgr
from .managers_bbr import BBRMgr
from .managers_bgp import BGPPeerMgrBase
from .managers_db import BGPDataBaseMgr
from .managers_intf import InterfaceMgr
from .managers_setsrc import ZebraSetSrc
from .managers_static_rt import StaticRouteMgr
from .runner import Runner, signal_handler
from .template import TemplateFabric
from .utils import read_constants
from .frr import FRR
from .vars import g_debug


def do_work():
    """ Main function """
    frr = FRR(["bgpd", "zebra", "staticd"])
    frr.wait_for_daemons(seconds=20)
    #
    common_objs = {
        'directory': Directory(),
        'cfg_mgr':   ConfigMgr(frr),
        'tf':        TemplateFabric(),
        'constants': read_constants(),
    }
    managers = [
        # Config DB managers
        BGPDataBaseMgr(common_objs, "CONFIG_DB", swsscommon.CFG_DEVICE_METADATA_TABLE_NAME),
        BGPDataBaseMgr(common_objs, "CONFIG_DB", swsscommon.CFG_DEVICE_NEIGHBOR_METADATA_TABLE_NAME),
        # Interface managers
        InterfaceMgr(common_objs, "CONFIG_DB", swsscommon.CFG_INTF_TABLE_NAME),
        InterfaceMgr(common_objs, "CONFIG_DB", swsscommon.CFG_LOOPBACK_INTERFACE_TABLE_NAME),
        InterfaceMgr(common_objs, "CONFIG_DB", swsscommon.CFG_VLAN_INTF_TABLE_NAME),
        InterfaceMgr(common_objs, "CONFIG_DB", swsscommon.CFG_LAG_INTF_TABLE_NAME),
        InterfaceMgr(common_objs, "CONFIG_DB", swsscommon.CFG_VLAN_SUB_INTF_TABLE_NAME),
        # State DB managers
        ZebraSetSrc(common_objs, "STATE_DB", swsscommon.STATE_INTERFACE_TABLE_NAME),
        # Peer Managers
        BGPPeerMgrBase(common_objs, "CONFIG_DB", swsscommon.CFG_BGP_NEIGHBOR_TABLE_NAME, "general", True),
        BGPPeerMgrBase(common_objs, "CONFIG_DB", swsscommon.CFG_BGP_INTERNAL_NEIGHBOR_TABLE_NAME, "internal", False),
        BGPPeerMgrBase(common_objs, "CONFIG_DB", "BGP_MONITORS", "monitors", False),
        BGPPeerMgrBase(common_objs, "CONFIG_DB", "BGP_PEER_RANGE", "dynamic", False),
        # AllowList Managers
        BGPAllowListMgr(common_objs, "CONFIG_DB", "BGP_ALLOWED_PREFIXES"),
        # BBR Manager
        BBRMgr(common_objs, "CONFIG_DB", "BGP_BBR"),
        # Static Route Managers
        StaticRouteMgr(common_objs, "CONFIG_DB", "STATIC_ROUTE"),
    ]
    runner = Runner(common_objs['cfg_mgr'])
    for mgr in managers:
        runner.add_manager(mgr)
    runner.run()


def main():
    rc = 0
    try:
        syslog.openlog('bgpcfgd')
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        do_work()
    except KeyboardInterrupt:
        log_notice("Keyboard interrupt")
    except RuntimeError as exc:
        log_crit(str(exc))
        rc = -2
        if g_debug:
            raise
    except Exception as exc:
        log_crit("Got an exception %s: Traceback: %s" % (str(exc), traceback.format_exc()))
        rc = -1
        if g_debug:
            raise
    finally:
        syslog.closelog()
    try:
        sys.exit(rc)
    except SystemExit:
        os._exit(rc)