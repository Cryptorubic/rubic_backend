from lastwill.contracts.submodels.ico import AbstractContractDetailsICO
from lastwill.contracts.submodels.common import *
from lastwill.consts import NET_DECIMALS, CONTRACT_GAS_LIMIT, CONTRACT_PRICE_USDT


@contract_details('Binance MyWish ICO')
class ContractDetailsBinanceICO(AbstractContractDetailsICO):
    eth_contract_token = models.ForeignKey(
        EthContract,
        null=True,
        default=None,
        related_name='binance_ico_details_token',
        on_delete=models.SET_NULL
    )
    eth_contract_crowdsale = models.ForeignKey(
        EthContract,
        null=True,
        default=None,
        related_name='binance_ico_details_crowdsale',
        on_delete=models.SET_NULL
    )

    @classmethod
    def min_cost(cls):
        network = Network.objects.get(name='BINANCE_SMART_MAINNET')
        cost = cls.calc_cost({}, network)
        return cost

    @staticmethod
    def calc_cost(kwargs, network):
        if NETWORKS[network.name]['is_free']:
            return 0
        return int(CONTRACT_PRICE_USDT['BINANCE_ICO'] * NET_DECIMALS['USDT'])
