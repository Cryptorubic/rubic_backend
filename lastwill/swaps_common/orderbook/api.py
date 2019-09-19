import datetime
import random
import string

from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ParseError, NotFound
from rest_framework.response import Response

from django.utils import timezone
from django.core.paginator import Paginator
from lastwill.contracts.serializers import ContractDetailsSWAPS2Serializer
from lastwill.contracts.submodels.common import Contract, send_in_queue
from lastwill.contracts.submodels.swaps import ContractDetailsSWAPS2
from lastwill.swaps_common.orderbook.models import OrderBookSwaps
from lastwill.swaps_common.mailing.models import SwapsNotificationDefaults
from lastwill.settings import SWAPS_ORDERBOOK_QUEUE

excluded_states = ['DONE', 'CANCELLED', 'POSTPONED']


def get_swap_from_orderbook(swap_id):
    backend_contract = OrderBookSwaps.objects.filter(id=swap_id).first()
    now = datetime.datetime.now(timezone.utc)

    if now > backend_contract.stop_date:
        if backend_contract.state not in excluded_states:
            backend_contract.state = 'EXPIRED'
            if backend_contract.swap_ether_contract:
                backend_contract.swap_ether_contract.state = 'EXPIRED'
                backend_contract.contract_state = backend_contract.swap_ether_contract.state
            else:
                backend_contract.contract_state = 'EXPIRED'
            backend_contract.save()
            backend_contract.refresh_from_db()

    saved_details = {
        'id': backend_contract.id,
        'name': backend_contract.name,
        'base_address': backend_contract.base_address,
        'base_limit': backend_contract.base_limit,
        'base_coin_id': backend_contract.base_coin_id,
        'quote_address': backend_contract.quote_address,
        'quote_limit': backend_contract.quote_limit,
        'quote_coin_id': backend_contract.quote_coin_id,
        'owner_address': backend_contract.owner_address,
        'stop_date': backend_contract.stop_date,
        'memo_contract': backend_contract.memo_contract,
        'unique_link': backend_contract.unique_link,
        'state': backend_contract.state,
        'user': backend_contract.user.id,
        'public': backend_contract.public,
        'broker_fee': backend_contract.broker_fee,
        'broker_fee_address': backend_contract.broker_fee_address,
        'broker_fee_base': backend_contract.broker_fee_base,
        'broker_fee_quote': backend_contract.broker_fee_quote,
        'comment': backend_contract.comment,
        'min_base_wei': backend_contract.min_base_wei,
        'min_quote_wei': backend_contract.min_quote_wei,
        'contract_state': backend_contract.contract_state,
        'created_date': backend_contract.created_date,
        'whitelist': backend_contract.whitelist,
        'whitelist_address': backend_contract.whitelist_address,
        'base_amount_contributed':  str(backend_contract.base_amount_contributed),
        'quote_amount_contributed': str(backend_contract.quote_amount_contributed),
        'notification_email': backend_contract.notification_email,
        'notification_tg': backend_contract.notification_telegram_name,
        'notification': backend_contract.notification
    }
    return saved_details


@api_view(http_method_names=['POST'])
def create_contract_swaps_backend(request):
    if request.user.is_anonymous:
        raise PermissionDenied

    contract_details = request.data

    base_address = contract_details['base_address'] if 'base_address' in contract_details else ""
    quote_address = contract_details['quote_address'] if 'quote_address' in contract_details else ""
    owner_address = contract_details['owner_address'] if 'owner_address' in contract_details else ""
    contract_name = contract_details['name'] if 'name' in contract_details else ""
    stop_date_conv = datetime.datetime.strptime(contract_details['stop_date'], '%Y-%m-%d %H:%M')
    base_coin_id_param = contract_details['base_coin_id'] if 'base_coin_id' in contract_details else 0
    quote_coin_id_param = contract_details['quote_coin_id'] if 'quote_coin_id' in contract_details else 0

    broker_fee = contract_details['broker_fee'] if 'broker_fee' in contract_details else False
    comment = contract_details['comment'] if 'comment' in contract_details else ""

    link = ''.join(
            random.choice(string.ascii_lowercase + string.digits) for _ in
            range(6)
        )

    memo = '0x' + ''.join(random.choice('abcdef' + string.digits) for _ in range(64))

    min_base_wei = contract_details['min_base_wei'] if 'min_base_wei' in contract_details else ""
    min_quote_wei = contract_details['min_quote_wei'] if 'min_quote_wei' in contract_details else ""
    whitelist = contract_details['whitelist'] if 'whitelist' in contract_details else False
    notification = contract_details['notification'] if 'notification' in contract_details else None

    notification_email = None
    notification_tg = None
    if notification:
        if not ('notification_email' in contract_details or 'notification_tg' in contract_details):
            raise ParseError('notificaion_email or notification_tg must be passed')

        notification_defaults = request.user.swapsnotificationdefaults_set.all()
        if not notification_defaults:
            notification_defaults = SwapsNotificationDefaults(user=request.user)
        else:
            notification_defaults = notification_defaults.first()

        notification_defaults.notification = notification

        if 'notification_email' in contract_details:
            notification_email = contract_details['notification_email']
            notification_defaults.email = notification_email
        if 'notification_tg' in contract_details:
            notification_tg = contract_details['notification_tg']
            notification_defaults.telegram_name = notification_tg

        notification_defaults.save()

    backend_contract = OrderBookSwaps(
            name=contract_name,
            base_address=base_address,
            base_limit=contract_details['base_limit'],
            base_coin_id=base_coin_id_param,
            quote_address=quote_address,
            quote_limit=contract_details['quote_limit'],
            quote_coin_id=quote_coin_id_param,
            owner_address=owner_address,
            stop_date=stop_date_conv,
            public=contract_details['public'],
            unique_link=link,
            user=request.user,
            broker_fee=broker_fee,
            memo_contract=memo,
            comment=comment,
            min_base_wei=min_base_wei,
            min_quote_wei=min_quote_wei,
            whitelist=whitelist,
            base_amount_contributed=0,
            base_amount_total=0,
            quote_amount_contributed=0,
            quote_amount_total=0,
            notification_email=notification_email,
            notification_telegram_name=notification_tg,
            notification=notification
    )

    if broker_fee:
        backend_contract.broker_fee = contract_details['broker_fee']
        if 'broker_fee_address' in contract_details:
            backend_contract.broker_fee_address = contract_details['broker_fee_address']
        if 'broker_fee_base' in contract_details:
            backend_contract.broker_fee_base = contract_details['broker_fee_base']
        if 'broker_fee_quote' in contract_details:
            backend_contract.broker_fee_quote = contract_details['broker_fee_quote']

    if whitelist:
        backend_contract.whitelist_address = contract_details['whitelist_address']

    backend_contract.state = 'ACTIVE'
    backend_contract.contract_state = 'CREATED'
    backend_contract.save()

    details = get_swap_from_orderbook(swap_id=backend_contract.id)
    print('sending swap order in queue ', backend_contract.id, flush=True)
    send_in_queue(backend_contract.id, 'launch', SWAPS_ORDERBOOK_QUEUE)
    return Response(details)


@api_view(http_method_names=['GET'])
def show_contract_swaps_backend(request):
    if request.user.is_anonymous:
        raise PermissionDenied

    swap_id = request.query_params.get('swap_id', None)
    if swap_id is not None:
        details = get_swap_from_orderbook(swap_id=swap_id)
        if details['state'] != 'HIDDEN':
            return Response(details)
        else:
            raise NotFound
    else:
        raise ParseError


@api_view(http_method_names=['GET'])
def show_user_contract_swaps_backend(request):
    if request.user.is_anonymous:
        raise PermissionDenied

    orders_list = []
    orders = OrderBookSwaps.objects.filter(user=request.user)
    for order in orders:
        details = get_swap_from_orderbook(swap_id=order.id)
        if details['state'] != 'HIDDEN':
            orders_list.append(details)

    return Response(orders_list)


@api_view(http_method_names=['POST'])
def edit_contract_swaps_backend(request, swap_id):
    if request.user.is_anonymous:
        raise PermissionDenied

    if swap_id is None:
        raise ParseError

    swap_order = OrderBookSwaps.objects.filter(id=swap_id).first()

    if swap_order.state == 'HIDDEN':
        raise NotFound

    if request.user != swap_order.user:
        if not request.user.profile.is_swaps_admin:
            raise PermissionDenied

    params = request.data

    if 'name' in params:
        swap_order.name = params['name']
    if 'stop_date' in params:
        stop_date = datetime.datetime.strptime(params['stop_date'], '%Y-%m-%d %H:%M')
        swap_order.stop_date = stop_date
    if 'base_address' in params:
        swap_order.base_address = params['base_address']
    if 'base_limit' in params:
        swap_order.base_limit = params['base_limit']
    if 'base_coin_id' in params:
        swap_order.base_coin_id = params['base_coin_id']
    if 'quote_address' in params:
        swap_order.quote_address = params['quote_address']
    if 'quote_limit' in params:
        swap_order.quote_limit = params['quote_limit']
    if 'quote_coin_id' in params:
        swap_order.quote_coin_id = params['quote_coin_id']
    if 'owner_address' in params:
        swap_order.owner_address = params['owner_address']
    if 'owner_address' in params:
        swap_order.public = params['public']
    if 'broker_fee' in params:
        swap_order.broker_fee = params['broker_fee']
    if params['broker_fee']:
        swap_order.broker_fee = params['broker_fee']
        if 'broker_fee_address' in params:
            swap_order.broker_fee_address = params['broker_fee_address']
        if 'broker_fee_base' in params:
            swap_order.broker_fee_base = params['broker_fee_base']
        if 'broker_fee_quote' in params:
            swap_order.broker_fee_quote = params['broker_fee_quote']
    if 'min_base_wei' in params:
        swap_order.min_base_wei = params['min_base_wei']
    if 'min_quote_wei' in params:
        swap_order.min_quote_wei = params['min_quote_wei']
    if 'whitelist' in params:
        swap_order.whitelist = params['whitelist']
        swap_order.whitelist_address = params['whitelist']
    if 'notification' in params:
        swap_order.notification = params['notification']

    if swap_order.notification:
        if not ('notification_email' in params or 'notification_tg' in params):
            raise ParseError('notificaion_email or notification_tg must be passed')

        notification_defaults = request.user.swapsnotificationdefaults_set.all()
        if not notification_defaults:
            notification_defaults = SwapsNotificationDefaults(user=request.user)
        else:
            notification_defaults = notification_defaults.first()

        notification_defaults.notification = swap_order.notification

        if 'notification_email' in params:
            notification_email = params['notification_email']
            notification_defaults.notification_email = notification_email
        if 'notification_tg' in params:
            notification_tg = params['notification_tg']
            notification_defaults.telegram_name = notification_tg

        notification_defaults.save()

    swap_order.save()
    details = get_swap_from_orderbook(swap_id=swap_order.id)

    return Response(details)


@api_view(http_method_names=['GET'])
def get_swap_v3_for_unique_link(request):
    link = request.query_params.get('unique_link', None)
    if not link:
        raise PermissionDenied
    swaps_order = OrderBookSwaps.objects.filter(unique_link=link).first()
    if not swaps_order:
        raise PermissionDenied

    details = get_swap_from_orderbook(swaps_order.id)

    if details['state'] == 'HIDDEN':
        raise NotFound

    return Response(details)


@api_view(http_method_names=['GET'])
def get_swap_v3_public(request):
    backend_contracts = OrderBookSwaps.objects.filter(public=True)

    res = []
    for order in backend_contracts:
        if order.state != 'EXPIRED' and order.state == 'ACTIVE':
            res.append(get_swap_from_orderbook(order.id))

    return Response(res)


@api_view(http_method_names=['POST'])
def set_swaps_expired(request):
    expired = request.data
    orders_ids = expired['trades']
    swaps_ids = expired['contracts']

    now = datetime.datetime.now(timezone.utc)

    for id in orders_ids:
        order = OrderBookSwaps.objects.filter(id=id)
        if not order:
            raise ParseError('trade with id {order_id} not exist'.format(order_id=id))

        order = order.first()
        if now > order.stop_date:
            if order.state not in excluded_states:
                order.state = 'EXPIRED'
                if order.swap_ether_contract:
                    order.swap_ether_contract.state = 'EXPIRED'
                    order.contract_state = order.swap_ether_contract.state
                else:
                    order.contract_state = 'EXPIRED'
                order.save()

    for id in swaps_ids:
        swaps = Contract.objects.filter(id=id)
        if not swaps:
            raise ParseError('contract with {swaps_id} not exist'.format(swaps_id=id))

        swaps = swaps.first()
        if now > swaps.get_details().stop_date:
            if swaps.contract.state not in excluded_states:
                swaps.contract.state = 'EXPIRED'
                swaps.contract.save()

    return Response({'result': 'ok'})


@api_view(http_method_names=['POST'])
def delete_swaps_v3(request):
    order_id = request.data['id']

    order = OrderBookSwaps.objects.filter(id=order_id)
    if not order:
        raise ParseError

    order = order.first()
    order.state = 'HIDDEN'
    order.save()
    return Response({"result": order.id})


@api_view(http_method_names=['POST'])
def cancel_swaps_v3(request):
    order_id = request.data['id']

    order = OrderBookSwaps.objects.filter(id=order_id)
    if not order:
        raise ParseError

    order = order.first()
    if not (order.base_address and order.quote_address):
        order.state = 'CANCELLED'
        order.contract_state = 'CANCELLED'
        if order.swap_ether_contract:
            order.swap_ether_contract.state = 'CANCELLED'
        order.save()
        return Response({"result": order.id})


@api_view(http_method_names=['POST', 'DELETE'])
def admin_delete_swaps_v3(request):
    order_id = request.data['id']

    if not request.user.profile.is_swaps_admin:
        raise PermissionDenied

    order = OrderBookSwaps.objects.filter(id=order_id)
    if not order:
        raise ParseError

    order = order.first()

    if order.base_address and order.quote_address:
        if not order.contract_state == 'CREATED':
            raise ParseError  # only for created
        else:
            order.swap_ether_contract.delete()
            order.delete()
    else:
        order.delete()

    return Response({"result": order_id})


@api_view(http_method_names=['GET'])
def get_non_active_orders(request):
    p = request.query_params.get('p', 1)
    if p and not isinstance(p, int):
        raise ParseError('page number must be int')

    order_list = OrderBookSwaps.objects.all().exclude(state__in=['ACTIVE', 'HIDDEN'])
    paginator = Paginator(order_list, 100)
    orders = paginator.page(p)
    res = []
    for row in orders:
        res.append(get_swap_from_orderbook(row.id))

    return res
