from lastwill.contracts.submodels.deffered import AbstractContractDetailsDelayedPayment
from lastwill.contracts.submodels.common import *
from lastwill.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT, CONTRACT_PRICE_USDT


@contract_details('Binance Deferred payment contract')
class ContractDetailsBinanceDelayedPayment(AbstractContractDetailsDelayedPayment):

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='BINANCE_SMART_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        return CONTRACT_PRICE_USDT['BINANCE_DEFFERED'] * NET_DECIMALS['USDT']
