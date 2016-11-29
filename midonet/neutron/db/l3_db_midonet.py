# Copyright (C) 2015 Midokura SARL.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import netaddr
from oslo_utils import excutils
from sqlalchemy import orm

from neutron_lib import constants as n_const

from neutron.callbacks import events
from neutron.callbacks import exceptions
from neutron.callbacks import registry
from neutron.callbacks import resources
from neutron.db import l3_db
from neutron.db import l3_gwmode_db
from neutron.db import models_v2
from neutron.extensions import l3


class MidonetL3DBMixin(l3_gwmode_db.L3_NAT_db_mixin):
    # TODO(kengo): This is temporary workaround until upstream adds a check
    # for router deletion in l3_db

    def _check_router_not_in_use(self, context, router_id):
        try:
            kwargs = {'context': context, 'router_id': router_id}
            registry.notify(
                resources.ROUTER, events.BEFORE_DELETE, self, **kwargs)
        except exceptions.CallbackFailure as e:
            with excutils.save_and_reraise_exception():
                if len(e.errors) == 1:
                    raise e.errors[0].error
                raise l3.RouterInUse(router_id=router_id, reason=e)

    def get_router_for_floatingip(self, context, internal_port,
            internal_subnet, external_network_id):
        # REVISIT(yamamoto): These direct manipulation of core-plugin db
        # resources is not ideal.
        gw_port = orm.aliased(models_v2.Port, name="gw_port")
        routerport_qry = context.session.query(
            l3_db.RouterPort.router_id,
            models_v2.IPAllocation.ip_address
        ).join(
            models_v2.Port, models_v2.IPAllocation
        ).filter(
            models_v2.Port.network_id == internal_port['network_id'],
            l3_db.RouterPort.port_type.in_(
                n_const.ROUTER_INTERFACE_OWNERS
            ),
            models_v2.IPAllocation.subnet_id == internal_subnet['id']
        ).join(
            gw_port, gw_port.device_id == l3_db.RouterPort.router_id
        ).filter(
            gw_port.network_id == external_network_id,
        ).distinct()

        first_router_id = None
        for router_id, interface_ip in routerport_qry:
            if interface_ip == internal_subnet['gateway_ip']:
                return router_id
            if not first_router_id:
                first_router_id = router_id
        if first_router_id:
            return first_router_id

        raise l3.ExternalGatewayForFloatingIPNotFound(
            subnet_id=internal_subnet['id'],
            external_network_id=external_network_id,
            port_id=internal_port['id'])

    def _subnet_has_fip(self, context, router_id, subnet_id):
        # Return True if the subnet has one of floating IPs for the router
        subnet = self._core_plugin.get_subnet(context, subnet_id)
        subnet_cidr = netaddr.IPNetwork(subnet['cidr'])
        fip_qry = context.session.query(l3_db.FloatingIP)
        fip_qry = fip_qry.filter_by(router_id=router_id)
        for fip_db in fip_qry:
            if netaddr.IPAddress(fip_db['floating_ip_address']) in subnet_cidr:
                return True
        return False

    def router_gw_port_has_floating_ips(self, context, router_id):
        router = self._get_router(context, router_id)
        return any([self._subnet_has_fip(context, router_id, ip['subnet_id'])
            for ip in router.gw_port['fixed_ips']])

    def find_next_hop_for_fip(self, context, floatingip_db):
        # Find a next-hop address for a route from the floating_network_id
        # network to the floating-ip.
        # NOTE(tidwellr) use admin context here
        # tenant may not own the router and that's OK on a FIP association
        router_id = floatingip_db.router_id
        router = self._get_router(context.elevated(), router_id)
        gw_port = None
        for rp in router.attached_ports:
            if rp.port.network_id == floatingip_db.floating_network_id:
                gw_port = rp.port
                break
        if not gw_port:
            return None
        for fixed_ip in gw_port.fixed_ips:
            addr = netaddr.IPAddress(fixed_ip.ip_address)
            if addr.version == n_const.IP_VERSION_4:
                return fixed_ip.ip_address

    # REVISIT(yamamoto): This method is a copy of the base class method,
    # modified to use find_next_hop_for_fip hook.
    def _update_fip_assoc(self, context, fip, floatingip_db, external_port):
        previous_router_id = floatingip_db.router_id
        port_id, internal_ip_address, router_id = (
            self._check_and_get_fip_assoc(context, fip, floatingip_db))
        update = {'fixed_ip_address': internal_ip_address,
                  'fixed_port_id': port_id,
                  'router_id': router_id,
                  'last_known_router_id': previous_router_id}
        if 'description' in fip:
            update['description'] = fip['description']
        floatingip_db.update(update)
        next_hop = None
        if router_id:
            next_hop = self.find_next_hop_for_fip(context, floatingip_db)
        return {'fixed_ip_address': internal_ip_address,
                'fixed_port_id': port_id,
                'router_id': router_id,
                'last_known_router_id': previous_router_id,
                'floating_ip_address': floatingip_db.floating_ip_address,
                'floating_network_id': floatingip_db.floating_network_id,
                'floating_ip_id': floatingip_db.id,
                'next_hop': next_hop,
                'context': context}
