import re
from errno import ENOENT, EROFS, ENOTSUP, EIO
from stat import S_IFDIR, S_IFLNK, S_IFREG, S_IRUSR, S_IWUSR
from sys import argv, exit
import os

from upbankapi import Client, NotAuthorizedException, UpBankException
from fuse import FUSE, FuseOSError, Operations

class PathRegexes:
    # monies = re.compile(r'^(-)?\$?(\d+)\.?(\d{0,2})$')
    account = re.compile(r'^/([^/]+)/')
    account_type = re.compile(r'^/([^/]+)/(spending|saver)$')
    balance = re.compile(r'^/(?:([^/]+)/(balance)|(unallocated))/(?:\$?(\d+)\.?(\d{0,2}))?$')
    transactions = re.compile(r'^/([^/]+)/(?:(transactions)/(?:(\d{4})/(?:(\d{2})/(?:(\d{2})/(?:([^/]+)/(?:(amount|category|description|message|settled|status)|(tags)/([^/]+)?)?)?)?)?)?)$')

class UpFuseOperations(Operations):
    """
    This class should be subclassed and passed as an argument to FUSE on
    initialization. All operations should raise a FuseOSError exception on
    error.
    When in doubt of what an operation should do, check the FUSE header file
    or the corresponding system call man page.
    """

    def __init__(self, client: Client):
        self.upapi = client
        self.moneypool = MoneyPool()

    def _total_unallocated(self):
        return sum(self.moneypool.total())

    def chmod(self, path, mode):
        # chmod is useless to us
        raise FuseOSError(EROFS)

    def chown(self, path, uid, gid):
        # chown is useless to us
        raise FuseOSError(EROFS)

    def link(self, target, source):
        # ln is useless to us
        raise FuseOSError(EROFS)

    def mkdir(self, path, mode):
        # mkdir is useless to us
        raise FuseOSError(EROFS)

    def mknod(self, path, mode, dev):
        # mknod is useless to us
        raise FuseOSError(EROFS)

    def readlink(self, path):
        # readlink is useless to us
        raise FuseOSError(ENOENT)

    def removexattr(self, path, name):
        # removexattr is useless to us
        raise FuseOSError(ENOTSUP)

    def rename(self, old, new):
        # rename is useless to us
        raise FuseOSError(EROFS)

    def rmdir(self, path):
        # rmdir is useless to us
        raise FuseOSError(EROFS)

    def setxattr(self, path, name, value, options, position=0):
        # setxattr is useless to us
        raise FuseOSError(ENOTSUP)

    def symlink(self, target, source):
        # symlink is useless to us
        raise FuseOSError(EROFS)

    def truncate(self, path, length, fh=None):
        # truncate is useless to us
        raise FuseOSError(EROFS)

    def unlink(self, path):
        # unlink is useless to us
        raise FuseOSError(EROFS)

    def write(self, path, data, offset, fh):
        # write is useless to us
        raise FuseOSError(EROFS)

    def create(self, path, mode, fi=None):
        """
        When raw_fi is False (default case), fi is None and create should
        return a numerical file handle.
        When raw_fi is True the file handle should be set directly by create
        and return 0.
        """

        raise FuseOSError(EROFS)

    def parse_path(self, path: str):
        """
        Parses the given path against the UpFS hierarchy.
        :param path: Path to validate
        :return: True if the path is within the hierarchy, otherwise False
        """

        # Match the path to the balance spec
        match = PathRegexes.balance.match(path)
        if not match:
            # Doesn't match path spec
            return False
        elif match.group(3):
            # Cannot add to unallocated
            raise FuseOSError(EROFS)

        # Extract the details from it
        account_str = match.group(1)
        dollars = float(match.group(4)) if match.group(4) else 0
        cents = float(match.group(5)) if match.group(5) else 0
        if not dollars and not cents:
            # Cannot make the directory itself
            raise FuseOSError(EROFS)
        amount = dollars + (cents / 100)

        # Parse the account
        try:
            account = self.upapi.account(account_str)
        except UpBankException:
            # Something went wrong getting the account
            raise FuseOSError(EIO)

        # Make sure the funds can be moved
        if amount > self._total_unallocated():
            # Can't credit funds - not enough available in the unallocated pool
            raise FuseOSError(ENOTSUP)

        # Move the funds
        withdrawn_amounts = self.moneypool.withdraw(amount)
        for account, amount in withdrawn_amounts:
            # TODO: Move money around with the Up API once it can do that
            pass

        return 0

    @staticmethod
    def _parse_dollars_cents(dollars: str, cents: str):
        """
        Parses the given dollar and cent values as a single float value
        :param dollars: Dollars
        :param cents: Cents
        :return: Float containing the total amount or None if neither value was provided
        """

        if not dollars and not cents:
            # Be specific in returning None to indicate neither value was provided
            return None
        else:
            # Convert and sum both values
            dollars_f = float(dollars) if dollars else 0
            cents_f = float(cents) if cents else 0
            return dollars_f + (cents_f / 100)

    def getattr(self, path, fh=None):
        """
        Returns a dictionary with keys identical to the stat C structure of
        stat(2).
        st_atime, st_mtime and st_ctime should be floats.
        NOTE: There is an incombatibility between Linux and Mac OS X
        concerning st_nlink of directories. Mac OS X counts all files inside
        the directory, while Linux counts only the subdirectories.
        """

        # TODO: Figure out a way to define path specs much like a web API endpoint
        #       complete with path variables. Then find a way to check different path
        #       specs (i.e. /unallocated/ vs /Spending/bal/
        #       vs /Saver/transactions/2020/August/13/Oreo Cafe/)

        # Match the path to the balance spec
        match = PathRegexes.balance.match(path)
        if match:
            # Try parse the account and get the balance
            account = None
            balance = None
            if match.group(1):
                try:
                    account = self.upapi.account(match.group(1))
                    balance = account.balance
                except UpBankException:
                    raise FuseOSError(EIO)
            else:
                balance = self.moneypool.total()

            # Double-check that this is the current balance, otherwise throw a not found error
            if self._parse_dollars_cents(match.group(4), match.group(5)) != balance:
                # Balance doesn't match, so technically this file can't exist
                raise FuseOSError(ENOENT)

            return 0

        # Match the path to the transaction spec
        match = PathRegexes.transactions.match(path)
        if match:
            # Try parse the transaction details
            # TODO: The above
            transaction_str = None

            # Try parse the account and get the transaction
            try:
                account = self.upapi.account(match.group(1))
                page = account.transactions()
            except UpBankException:
                raise FuseOSError(EIO)

            # Iterate over all the transactions in this account to find this one
            transaction = None
            while page and not transaction:
                for _transaction in page:
                    if _transaction.id == transaction_str:
                        transaction = _transaction
                        break

                # Be safe when getting the next page
                try:
                    page = page.next()
                except UpBankException:
                    raise FuseOSError(EIO)

        # TODO: Rest of the regex matching

        return dict(
            st_mode=(S_IFREG | S_IRUSR | S_IWUSR),
            st_nlink=1,
            st_size=0,
            st_ctime=,
            st_mtime=time(),
            st_atime=time()
        )

        if path != '/':
            raise FuseOSError(ENOENT)
        return dict(st_mode=(S_IFDIR | 0o755), st_nlink=2)

    def getxattr(self, path, name, position=0):
        raise FuseOSError(ENOTSUP)

    def listxattr(self, path):
        return []

    def open(self, path, flags):
        """
        When raw_fi is False (default case), open should return a numerical
        file handle.
        When raw_fi is True the signature of open becomes:
            open(self, path, fi)
        and the file handle should be set directly.
        """

        return 0

    def opendir(self, path):
        """Returns a numerical file handle."""

        return 0

    def read(self, path, size, offset, fh):
        """Returns a string containing the data requested."""

        raise FuseOSError(EIO)

    def readdir(self, path, fh):
        """
        Can return either a list of names, or a list of (name, attrs, offset)
        tuples. attrs is a dict as in getattr.
        """

        return ['.', '..']

    def release(self, path, fh):
        return 0

    def releasedir(self, path, fh):
        return 0

    def statfs(self, path):
        """
        Returns a dictionary with keys identical to the statvfs C structure of
        statvfs(3).
        On Mac OS X f_bsize and f_frsize must be a power of 2
        (minimum 512).
        """

        return {}

    def utimens(self, path, times=None):
        """Times is a (atime, mtime) tuple. If None use current time."""

        return 0


class MoneyPool:
    """
    Utility class that tracks multiple accounts and treats their funds as a single pool to withdraw from.
    """

    def __init__(self):
        self._accounts = dict()

    def total(self):
        """
        Returns the total funds across all accounts.
        """
        return sum(self._accounts.values())

    def totals(self):
        """
        Returns a dict the total funds for each account.
        """
        return dict(self._accounts)

    def deposit(self, account, amount):
        """
        Makes a deposit to the given account with the given amount.
        :param account: Account to deposit into
        :param amount: Amount to deposit
        """
        if not self._accounts[account]:
            self._accounts[account] = amount
        else:
            self._accounts[account] = self._accounts[account] + amount

    def withdraw(self, amount):
        """
        Withdraws the given amount from the pool.
        This will empty accounts sequentially until the withdrawal is completed.
        :param amount: Amount to withdraw
        :return: Dict containing each account and the amount withdrawn from them
        """
        withdrawn_amounts = dict()

        # Make sure the funds are available
        if self.total() < amount:
            return withdrawn_amounts

        for account, balance in self._accounts.items():
            # Stop guzzling funds if we have taken what we need
            if amount == 0:
                break

            # Withdraw the maximum we can from this account
            self._accounts[account] = max(balance - amount, 0)
            withdrawn_amounts[account] = max(min(0, balance - (balance - amount)), balance)

            # and take a chunk out of the amount left
            amount = amount - (balance - amount)

        return withdrawn_amounts


if __name__ == '__main__':
    if len(argv) != 2:
        print('usage: %s <mountpoint>' % argv[0])
        exit(1)

    # Try read our Up token
    with open('token', 'r') as file:
        token = file.readline().strip()

    # Authenticate with Up
    client = Client(token=token)
    try:
        user_id = client.ping()
        #print('Authorized as {0}.'.format(user_id))
    except NotAuthorizedException:
        print('The Up token is invalid. Die.')
        exit(1)

    # Create and mount our FUSE instance
    fuse = FUSE(UpFuseOperations(client), argv[1], foreground=False)
