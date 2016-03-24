The Unvanquished Master Server
Requires Python 2.6

Protocol for this is pretty simple.
Accepted incoming messages:
 * 'heartbeat <game>\\n'
        <game> is ignored for the time being (it's always Unvanquished in any
        case). It's a request from a server for the master to start tracking it
        and reporting it to clients. Usually the master will verify the server
        before accepting it into the server list.
 * 'getservers <protocol> [empty] [full]'
        A request from the client to send the list of servers.
 * 'getserversExt <game> <protocol> [ipv4|ipv6|dual] [empty] [full]'
        A request from the client to send the list of servers.
        'dual' requests that info about which are dual-stack is also returned.
