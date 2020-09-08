import re
from datetime import datetime, date
from errno import ENOENT, EROFS, ENOTSUP, EIO
from stat import S_IFDIR, S_IFLNK, S_IFREG, S_IRUSR, S_IWUSR
from sys import argv, exit
import os

from upbankapi import Client, NotAuthorizedException, UpBankException
from fuse import FUSE, FuseOSError, Operations

class PathRegexes:
    account = re.compile(r'^/(?:([^/]+)/(balance|spending|saver)?)$')
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

    def getattr(self, path, fh=None):
        """
        Returns a dictionary with keys identical to the stat C structure of
        stat(2).
        st_atime, st_mtime and st_ctime should be floats.
        NOTE: There is an incombatibility between Linux and Mac OS X
        concerning st_nlink of directories. Mac OS X counts all files inside
        the directory, while Linux counts only the subdirectories.
        """

        # Match the path to the account spec
        match = PathRegexes.account.match(path)
        if match:
            # Try parse the account
            if match.group(1):
                try:
                    account = self.upapi.account(match.group(1))
                except UpBankException:
                    raise FuseOSError(EIO)

            if not match.group(2):
                # TODO: Root account dir
                pass
            elif match.group(2) == 'balance':
                # TODO: Balance
                balance = account.balance
                pass
            elif match.group(2) == 'spending':
                # TODO: Spending flag
                pass
            elif match.group(2) == 'saver':
                # TODO: Saver flag
                pass
            else:
                # Invalid path
                raise FuseOSError(ENOENT)

        # Match the path to the transaction spec
        match = PathRegexes.transactions.match(path)
        if match:
            # Try parse the transaction details
            account_str = match.group(1)
            if not match.group(2):
                # No 'transactions' in the path, something has gone horribly wrong
                raise FuseOSError(EIO)
            year = match.group(3)
            month = match.group(4)
            day = match.group(5)
            payee = match.group(6)
            detail = match.group(7)
            if match.group(8):
                # Tags
                detail = 'tags'
                tag = match.group(9)

            # Try parse the account and get the transaction
            try:
                account = self.upapi.account(match.group(1))
                page = account.transactions()
            except UpBankException:
                raise FuseOSError(EIO)

            # Make sure we have the whole path before trying to get the transaction
            if year and month and day and payee:
                # Iterate over all the transactions in this account to find this one
                transaction = None
                while page and not transaction:
                    for _transaction in page:
                        if _transaction.id == payee and _transaction.created_at.date() == date(int(year), int(month), int(day)):
                            transaction = _transaction
                            break

                    # Be safe when getting the next page
                    try:
                        page = page.next()
                    except UpBankException:
                        raise FuseOSError(EIO)

                if not transaction:
                    # Couldn't find the transaction, report file not found
                    raise FuseOSError(ENOENT)

                if detail:
                    if detail == 'tags':
                        # TODO: Tags
                        pass
                    elif detail == 'amount':
                        # TODO: Amount
                        pass
                    elif detail == 'category':
                        # TODO: Category
                        pass
                    elif detail == 'description':
                        # TODO: Description
                        pass
                    elif detail == 'message':
                        # TODO: Message
                        pass
                    elif detail == 'settled':
                        # TODO: Settled
                        pass
                    elif detail == 'status':
                        # TODO: Status
                        pass
                    else:
                        # Not a valid detail
                        raise FuseOSError(ENOENT)
            elif year and month and day:
                # TODO: Get the transactions at this date
                pass
            elif year and month:
                # TODO: Get the days in this month with a transaction
                pass
            elif year:
                # TODO: Get the months in this year with a transaction
                pass
            else:
                # TODO: Get the years with a transaction
                pass

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

        # TODO: Validate the file path and return the data
        pass

    def readdir(self, path, fh):
        """
        Can return either a list of names, or a list of (name, attrs, offset)
        tuples. attrs is a dict as in getattr.
        """

        # TODO: Validate the file path and return a list of the contents
        return ['.', '..']

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

class FileDescriptor:
    """
    Common class used to represent virtual 'files' within UpFS.
    Contains all attributes and content that needs to be displayed to the operating system.
    """
    # TODO: Get all the attributes needed and plug them in here

    def __init__(self, path: str):
        self.path = path
        self.attributes = dict(
            st_mode=None,
            st_nlink=None,
            st_size=None,
            st_ctime=None,
            st_mtime=None,
            st_atime=None
        )
        self.content = None
        self.is_dir = path.endswith('/')


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
