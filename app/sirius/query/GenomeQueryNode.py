from sirius.mongo import GenomeNodes
from sirius.core.utilities import HashableDict
from sirius.analysis.Bed import Bed


def find_gid(mongo_filter, limit=100000):
    """ Cached funtion to find the GenomeNodes and return their IDs """
    mongo_filter = HashableDict(mongo_filter)
    # if we previously have executed the filter, check previous limit
    max_limit = find_gid.max_limit.get(mongo_filter, 0)
    if limit == max_limit:
        result_ids = find_gid.cached_ids[mongo_filter]
    elif limit < max_limit:
        cached_ids = find_gid.cached_ids[mongo_filter]
        result_ids = {d for i, d in enumerate(cached_ids) if i < limit}
    else:
        result_ids = set(d['_id'] for d in GenomeNodes.find(mongo_filter, {'_id':1}, limit=limit))
        find_gid.cached_ids[mongo_filter] = result_ids
        find_gid.max_limit[mongo_filter] = limit
    # limit the size of the cache to save memory
    if len(find_gid.cached_ids) > 10000:
        # we pop the earliest key
        key = next(iter(find_gid.cached_ids.keys()))
        find_gid.cached_ids.pop(key)
        find_gid.max_limit.pop(key)
    return result_ids

find_gid.cached_ids, find_gid.max_limit = dict(), dict()


class GenomeQueryNode(object):
    def __init__(self, qfilter=dict(), edges=None, edge_rule=None, arithmetics=[], limit=0, verbose=False):
        self.filter = qfilter
        self.edges = [] if edges == None else edges
        # edge_rule: 0 means "and", 1 means "or", 2 means "not"
        self.edge_rule = 0 if edge_rule == None else edge_rule
        self.arithmetics = arithmetics
        self.limit = int(limit)
        self.verbose = verbose

    def find(self, projection=None):
        """
        Find all nodes from GenomeNodes, based on self.filter and the edge connected.
        Return a cursor of MongoDB.find() query, or an empty list if none found
        """
        if self.verbose:
            print(self.filter)
        result_ids = self.findid()
        query = {'_id': {"$in": list(result_ids)}}
        if projection != None:
            return GenomeNodes.find(query, limit=self.limit, projection=projection)
        else:
            return GenomeNodes.find(query, limit=self.limit)

    def findid(self):
        """
        Find all nodes from GenomeNodes, based on self.filter and the edge connected
        Return a set that contain strings of node['_id']
        """
        # get the results for all edges
        if len(self.edges) > 0:
            first_edgenode = self.edges[0]
            result_ids = first_edgenode.find_from_id()
            for edgenode in self.edges[1:]:
                # stop here if we have nothing left
                if len(result_ids) == 0 and self.edge_rule != 1: return set()
                # find the from_ids of the next edge
                e_ids = edgenode.find_from_id()
                if self.edge_rule == 0: # AND
                    result_ids &= e_ids
                elif self.edge_rule == 1: # OR
                    result_ids |= e_ids
                elif self.edge_rule == 2: # NOT
                    result_ids -= e_ids
            if len(result_ids) == 0: return set()
            # intersect with the ids for this node
            if self.filter:
                result_ids &= find_gid(self.filter, self.limit)
        else:
            # the result ids of this filter
            result_ids = find_gid(self.filter, self.limit)
        if not self.arithmetics or not result_ids:
            return result_ids
        # Use the bedtools to do arithmics
        # do the arithmetics one by one
        for ar in self.arithmetics:
            operator = ar['operator']
            if operator == 'union':
                for target in ar['targets']:
                    result_ids |= target.findid()
            elif operator == 'window':
                bed = Bed()
                bed.load_from_ids(result_ids)
                window_size = ar['windowSize']
                for target in ar['targets']:
                    target_bed = Bed(target)
                    bed = bed.window(target_bed, window=window_size)
                result_ids = bed.gids()
            elif operator == 'intersect':
                bed = Bed()
                bed.load_from_ids(result_ids)
                for target in ar['targets']:
                    target_bed = Bed(target)
                    bed = bed.intersect(target_bed)
                result_ids = bed.gids()
        return result_ids





