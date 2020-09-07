from upbankapi import Client, NotAuthorizedException

if __name__ == '__main__':
    # Try read our Up token
    with open('token', 'r') as file:
        token = file.readline().strip()

    client = Client(token=token)

    # optionally check the token is valid
    try:
        user_id = client.ping()
        print('Authorized as {0}.'.format(user_id))
    except NotAuthorizedException:
        print('The token is invalid. Die.')
        exit(1)

    for account in client.accounts():
        for transaction in account.transactions():
            print(transaction)