from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List


class SecuritiesError(Exception):
    """Base exception for securities trading errors."""


class StockNotFoundError(SecuritiesError):
    def __init__(self, symbol: str) -> None:
        super().__init__(f"'{symbol}' 종목은 등록되어 있지 않습니다.")


class AuthenticationError(SecuritiesError):
    def __init__(self) -> None:
        super().__init__("거래 비밀번호가 올바르지 않습니다.")


class InsufficientCashError(SecuritiesError):
    def __init__(self) -> None:
        super().__init__("보유 현금이 부족하여 매수할 수 없습니다.")


class InsufficientStockError(SecuritiesError):
    def __init__(self) -> None:
        super().__init__("보유 주식 수량이 부족하여 매도할 수 없습니다.")


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Investor:
    investor_id: str
    name: str


@dataclass(frozen=True)
class Stock:
    symbol: str
    company_name: str
    market: str
    current_price: Decimal

    def display(self) -> str:
        return (
            f"{self.symbol} | {self.company_name:<20} | "
            f"{self.market:<5} | {self.current_price:>10,.0f} KRW"
        )


@dataclass(frozen=True)
class Order:
    order_id: str
    account_number: str
    stock: Stock
    side: OrderSide
    quantity: int
    ordered_at: datetime

    @property
    def total_amount(self) -> Decimal:
        return self.stock.current_price * Decimal(self.quantity)


@dataclass(frozen=True)
class Trade:
    trade_id: str
    order_id: str
    stock_symbol: str
    stock_name: str
    side: OrderSide
    quantity: int
    price: Decimal
    commission: Decimal
    cash_after: Decimal
    executed_at: datetime

    def summary(self) -> str:
        side_label = "매수" if self.side == OrderSide.BUY else "매도"
        return (
            f"{self.executed_at:%Y-%m-%d %H:%M:%S} | "
            f"{side_label:<2} | "
            f"{self.stock_symbol:<6} | "
            f"{self.stock_name:<20} | "
            f"수량={self.quantity:<3} | "
            f"가격={self.price:>10,.0f} | "
            f"수수료={self.commission:>6,.0f} | "
            f"현금={self.cash_after:>10,.0f}"
        )


class StockCatalog:
    def __init__(self) -> None:
        self._stocks: Dict[str, Stock] = {}

    def add(self, stock: Stock) -> None:
        self._stocks[stock.symbol] = stock

    def find_by_symbol(self, symbol: str) -> Stock:
        normalized_symbol = symbol.strip()
        if normalized_symbol not in self._stocks:
            raise StockNotFoundError(normalized_symbol)
        return self._stocks[normalized_symbol]

    def print_available_stocks(self) -> None:
        print("\n=== 거래 가능 종목 ===")
        for stock in self._stocks.values():
            print(stock.display())


class BrokerageAccount:
    def __init__(self, account_number: str, owner: Investor, cash_balance: Decimal) -> None:
        self._account_number = account_number
        self._owner = owner
        self._cash_balance = cash_balance
        self._holdings: Dict[str, int] = {}

    @property
    def account_number(self) -> str:
        return self._account_number

    @property
    def owner(self) -> Investor:
        return self._owner

    @property
    def cash_balance(self) -> Decimal:
        return self._cash_balance

    def holdings(self) -> Dict[str, int]:
        return dict(self._holdings)

    def quantity_of(self, symbol: str) -> int:
        return self._holdings.get(symbol, 0)

    def buy(self, stock: Stock, quantity: int, commission: Decimal) -> None:
        self._validate_quantity(quantity)
        required_cash = stock.current_price * Decimal(quantity) + commission
        if self._cash_balance < required_cash:
            raise InsufficientCashError()

        self._cash_balance -= required_cash
        self._holdings[stock.symbol] = self.quantity_of(stock.symbol) + quantity

    def sell(self, stock: Stock, quantity: int, commission: Decimal) -> None:
        self._validate_quantity(quantity)
        if self.quantity_of(stock.symbol) < quantity:
            raise InsufficientStockError()

        self._holdings[stock.symbol] -= quantity
        if self._holdings[stock.symbol] == 0:
            del self._holdings[stock.symbol]
        self._cash_balance += stock.current_price * Decimal(quantity) - commission

    def _validate_quantity(self, quantity: int) -> None:
        if quantity <= 0:
            raise ValueError("수량은 0보다 커야 합니다.")


class CommissionPolicy(ABC):
    @abstractmethod
    def calculate(self, amount: Decimal) -> Decimal:
        raise NotImplementedError


class KoreanStockCommissionPolicy(CommissionPolicy):
    def calculate(self, amount: Decimal) -> Decimal:
        fee = amount * Decimal("0.00015")
        return max(fee, Decimal("100"))


class AuthService:
    def __init__(self) -> None:
        self._password_by_investor_id: Dict[str, str] = {}

    def register_password(self, investor: Investor, password: str) -> None:
        self._password_by_investor_id[investor.investor_id] = password

    def authenticate(self, investor: Investor, password: str) -> None:
        if self._password_by_investor_id.get(investor.investor_id) != password:
            raise AuthenticationError()


class TradeLedger:
    def __init__(self) -> None:
        self._trades: List[Trade] = []
        self._next_trade_id = 1

    def record(self, order: Order, commission: Decimal, cash_after: Decimal) -> Trade:
        trade = Trade(
            trade_id=f"TR{self._next_trade_id:05d}",
            order_id=order.order_id,
            stock_symbol=order.stock.symbol,
            stock_name=order.stock.company_name,
            side=order.side,
            quantity=order.quantity,
            price=order.stock.current_price,
            commission=commission,
            cash_after=cash_after,
            executed_at=datetime.now(),
        )
        self._next_trade_id += 1
        self._trades.append(trade)
        return trade

    def history(self) -> List[Trade]:
        return list(self._trades)


class OrderService:
    def __init__(
        self,
        account: BrokerageAccount,
        auth_service: AuthService,
        trade_ledger: TradeLedger,
        commission_policy: CommissionPolicy,
    ) -> None:
        self._account = account
        self._auth_service = auth_service
        self._trade_ledger = trade_ledger
        self._commission_policy = commission_policy
        self._next_order_id = 1

    def place_order(
        self,
        stock: Stock,
        side: OrderSide,
        quantity: int,
        password: str,
    ) -> Trade:
        self._auth_service.authenticate(self._account.owner, password)
        order = self._create_order(stock, side, quantity)
        commission = self._commission_policy.calculate(order.total_amount)

        if side == OrderSide.BUY:
            self._account.buy(stock, quantity, commission)
        else:
            self._account.sell(stock, quantity, commission)

        return self._trade_ledger.record(order, commission, self._account.cash_balance)

    def _create_order(self, stock: Stock, side: OrderSide, quantity: int) -> Order:
        order = Order(
            order_id=f"OD{self._next_order_id:05d}",
            account_number=self._account.account_number,
            stock=stock,
            side=side,
            quantity=quantity,
            ordered_at=datetime.now(),
        )
        self._next_order_id += 1
        return order


class PortfolioService:
    def __init__(
        self,
        account: BrokerageAccount,
        stock_catalog: StockCatalog,
        trade_ledger: TradeLedger,
    ) -> None:
        self._account = account
        self._stock_catalog = stock_catalog
        self._trade_ledger = trade_ledger

    def print_portfolio(self) -> None:
        print("\n=== 내 포트폴리오 ===")
        print(f"투자자: {self._account.owner.name}")
        print(f"계좌번호: {self._account.account_number}")
        print(f"보유 현금: {self._account.cash_balance:,.0f} KRW")
        print("보유 종목:")
        if not self._account.holdings():
            print("- 보유 종목 없음")
        for symbol, quantity in self._account.holdings().items():
            stock = self._stock_catalog.find_by_symbol(symbol)
            print(f"- {stock.symbol} | {stock.company_name} | {quantity}주")

    def print_trade_history(self) -> None:
        print("\n=== 거래 내역 ===")
        if not self._trade_ledger.history():
            print("- 거래 내역 없음")
        for trade in self._trade_ledger.history():
            print(trade.summary())


class ConsoleApplication:
    def __init__(
        self,
        stock_catalog: StockCatalog,
        account: BrokerageAccount,
        order_service: OrderService,
        portfolio_service: PortfolioService,
    ) -> None:
        self._stock_catalog = stock_catalog
        self._account = account
        self._order_service = order_service
        self._portfolio_service = portfolio_service

    def run(self) -> None:
        print("증권사 IT 백엔드 주식 거래 시스템")
        while True:
            print("\n=== 메인 메뉴 ===")
            print("1) 종목 검색 및 거래")
            print("2) 내 자산 확인")
            print("3) 거래 내역 확인")
            print("q) 종료")
            menu = input("메뉴를 선택하세요: ").strip()

            if menu == "1":
                self._search_and_trade()
            elif menu == "2":
                self._portfolio_service.print_portfolio()
            elif menu == "3":
                self._portfolio_service.print_trade_history()
            elif menu.lower() == "q":
                print("프로그램을 종료합니다.")
                break
            else:
                print("[오류] 1, 2, 3, q 중 하나를 입력하세요.")

    def _search_and_trade(self) -> None:
        while True:
            self._stock_catalog.print_available_stocks()
            symbol = input("\n검색할 종목 코드를 입력하세요. 메인 메뉴로 돌아가려면 b 입력: ").strip()
            if not symbol:
                print("[오류] 005930, 000660, 035720 중 하나의 종목 코드를 입력하세요.")
                continue
            if symbol.lower() == "b":
                break

            try:
                stock = self._stock_catalog.find_by_symbol(symbol)
                self._handle_selected_stock(stock)
            except StockNotFoundError as error:
                print(f"[오류] {error}")
            except SecuritiesError as error:
                print(f"[오류] {error}")
            except ValueError as error:
                print(f"[오류] 잘못된 입력입니다: {error}")

    def _handle_selected_stock(self, stock: Stock) -> None:
        print(f"\n선택한 종목: {stock.display()}")
        action = input("원하는 작업을 선택하세요: 1) 매수  2) 매도  3) 뒤로가기 : ").strip()
        if action == "1":
            self._buy_stock(stock)
        elif action == "2":
            self._sell_stock(stock)
        elif action == "3":
            return
        else:
            print("[오류] 알 수 없는 선택입니다. 1, 2, 3 중 하나를 입력하세요.")

    def _buy_stock(self, stock: Stock) -> None:
        if stock.current_price > self._account.cash_balance:
            print("[오류] 현재가가 보유 현금보다 높아서 이 종목은 매수할 수 없습니다.")
            self._portfolio_service.print_portfolio()
            return

        quantity = int(input("매수할 수량을 입력하세요: "))
        password = input("거래 비밀번호를 입력하세요: ")
        trade = self._order_service.place_order(stock, OrderSide.BUY, quantity, password)
        print(f"[성공] 매수 주문이 체결되었습니다: {trade.summary()}")
        self._portfolio_service.print_portfolio()

    def _sell_stock(self, stock: Stock) -> None:
        quantity = int(input("매도할 수량을 입력하세요: "))
        password = input("거래 비밀번호를 입력하세요: ")
        trade = self._order_service.place_order(stock, OrderSide.SELL, quantity, password)
        print(f"[성공] 매도 주문이 체결되었습니다: {trade.summary()}")
        self._portfolio_service.print_portfolio()


def money(value: str) -> Decimal:
    return Decimal(value)


def build_application() -> ConsoleApplication:
    investor = Investor("I001", "kimsubin")
    account = BrokerageAccount("777-88-9999", investor, money("300000"))

    stock_catalog = StockCatalog()
    stock_catalog.add(Stock("005930", "Samsung Electronics", "KOSPI", money("72000")))
    stock_catalog.add(Stock("000660", "SK Hynix", "KOSPI", money("180000")))
    stock_catalog.add(Stock("035720", "Kakao", "KOSPI", money("56000")))

    auth_service = AuthService()
    auth_service.register_password(investor, "2468")

    trade_ledger = TradeLedger()
    commission_policy = KoreanStockCommissionPolicy()
    order_service = OrderService(account, auth_service, trade_ledger, commission_policy)
    portfolio_service = PortfolioService(account, stock_catalog, trade_ledger)

    return ConsoleApplication(stock_catalog, account, order_service, portfolio_service)


def main() -> None:
    app = build_application()
    app.run()


if __name__ == "__main__":
    main()
