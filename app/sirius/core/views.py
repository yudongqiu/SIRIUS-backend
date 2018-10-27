#==================================#
#            views.py              #
#----------------------------------#
#  Here sits all the api endpoints #
#==================================#

from flask import abort, request, send_from_directory
import os
import json
import time
import threading
import random
import subprocess
from sirius.main import app
from sirius.core.utilities import get_data_with_id, HashableDict, threadsafe_lru
from sirius.query.query_tree import QueryTree
from sirius.helpers.loaddata import loaded_contig_info, loaded_contig_info_dict, loaded_track_types_info, loaded_data_track_info_dict, loaded_data_tracks
from sirius.helpers.constants import TRACK_TYPE_SEQUENCE, TRACK_TYPE_FUNCTIONAL, TRACK_TYPE_3D, TRACK_TYPE_NETWORK, TRACK_TYPE_BOOLEAN, \
                                     QUERY_TYPE_GENOME, QUERY_TYPE_INFO, QUERY_TYPE_EDGE
from sirius.core.annotationtrack import get_annotation_query

from sirius.mongo import GenomeNodes, InfoNodes, Edges
from sirius.core.auth0 import requires_auth, get_user_profile

#**************************
#*     static urls        *
#**************************
# These urls will be served by Nginx if possible
@app.route('/')
@app.route('/index')
@requires_auth
def index():
    return send_from_directory("valis-dist", "index.html")

@app.route('/<path:path>')
@requires_auth
def send_file(path):
    return app.send_static_file(path)



#**************************
#*      /contig_info      *
#**************************

@app.route("/contig_info")
@requires_auth
def contig_info():
    """
    Endpoint for frontend to pre-fetch the available contigs and their dimensions

    Returns
    -------
    contig_info_list: list (json)
        A list of contig information, each being a dictionary

    Examples
    --------

    >>> print(contig_info())
    [
        {
            'name': 'chr1',
            'length': '248956422',
            'chromosome': 'chr1'
        },
        {
            'name': 'NT_187636.1',
            'length': '248807',
            'chromosome': '19'
        }
    ]

    """
    return json.dumps(loaded_contig_info)



#**************************
#*      /track_info       *
#**************************

@app.route("/track_info")
@requires_auth
def track_info():
    """
    Endpoint for rendering the selections in DataBrowser side panel.

    Returns
    -------
    track_info_list: list (json)
        The list of available track types.
        In the list, each track_info is a dictionary with three keys: 'track_type', 'title', 'description'

    """
    return json.dumps(loaded_track_types_info)



# This is the new endpoint that will replace /tracks to return real data
#**************************
#*       /datatracks      *
#**************************
from sirius.core.datatrack import get_sequence_data, get_signal_data, old_api_track_data

@app.route("/datatracks")
@requires_auth
def datatracks():
    """
    Endpoint for getting all available data tracks

    Returns
    -------
    loaded_data_tracks: list (json)
        The list of available track types.
        In the list, each track_info is a dictionary with keys: 'id', 'name'

    """
    return json.dumps([{'id': t['id'], 'name': t['name']} for t in loaded_data_tracks])

@app.route("/datatracks/<string:track_id>")
@requires_auth
def datatrack_info_by_id(track_id):
    """
    Endpoint for getting all available data tracks

    Returns
    -------
    track_info_dict: dictionary (json)
        The InfoNode that contains the metadata for track_id.

    """
    info = loaded_data_track_info_dict.get(track_id, None)
    if info == None:
        return abort(404, f'track {track_id} not found')
    track_info = {
        'id': info['_id'],
        'type': info['type']
    }
    return json.dumps(track_info)

@app.route("/datatracks/<string:track_id>/<string:contig>/<int:start_bp>/<int:end_bp>")
@requires_auth
def datatrack_get_data(track_id, contig, start_bp, end_bp):
    """Return the data for the given track and base pair range"""
    if start_bp > end_bp:
        return abort(404, 'start_bp > end_bp not allowed')
    sampling_rate = int(request.args.get('sampling_rate', default=1))
    if track_id == 'sequence':
        return get_sequence_data(track_id, contig, start_bp, end_bp, sampling_rate)
    else:
        aggregations = request.args.get('aggregations', default='none').split(',')
        return get_signal_data(track_id, contig, start_bp, end_bp, sampling_rate, aggregations)



# This part is still mock
#**************************
#*        /graphs         *
#**************************

@app.route("/graphs")
@requires_auth
def graphs():
    return json.dumps(["ld_score"])

@app.route("/graphs/<string:graph_id>/<string:annotation_id1>/<string:annotation_id2>/<int:start_bp>/<int:end_bp>")
@requires_auth
def graph(graph_id, annotation_id1, annotation_id2, start_bp, end_bp):
    start_bp = int(start_bp)
    end_bp = int(end_bp)

    sampling_rate = 1
    if request.args.get('sampling_rate'):
        sampling_rate = int(float(request.args.get('sampling_rate')))

    base_pair_offset = 0
    if request.args.get('base_pair_offset'):
        base_pair_offset = int(float(request.args.get('base_pair_offset')))

    if graph_id != "ld_score":
        abort(500, "Unknown graph : %s", graph_id)

    if annotation_id1 != "cross-track-test-1" or annotation_id2 != "cross-track-test-2":
        abort(500, "no graph available")

    # send edge scores
    set1 = []
    set2 = []
    if sampling_rate < 1000000:
        count = 0
        for i in range(0, 100000000, 500000):
            if i >= start_bp and i <= end_bp:
                annotation_name = "X%d" % count
                random.seed(annotation_name)
                set1.append(random.randint(0,1000000000))
            count += 1
        count = 0
        for i in range(0, 100000000, 500000):
            if i >= start_bp + base_pair_offset and i <= end_bp + base_pair_offset:
                annotation_name = "Y%d" % count
                random.seed(annotation_name)
                set2.append(random.randint(0,1000000000))
            count += 1

    edges = []
    for e1 in set1:
        for e2 in set2:
            random.seed("%d|%d" % (e1,e2))
            edges.append([e1, e2, random.random()])
    return json.dumps({
        "startBp" : start_bp,
        "endBp" : end_bp,
        "samplingRate": sampling_rate,
        "graphId": graph_id,
        "annotationIds": [annotation_id1, annotation_id2],
        "values": edges
    })




#**************************
#*     /distince_values   *
#**************************

@app.route("/distinct_values/<string:index>", methods=['POST'])
@requires_auth
def distinct_values(index):
    """ Return all possible values for a certain index for certain query """
    query = request.get_json()
    if not query:
        return abort(404, 'no query posted')
    # We restrict the choices here to prevent crashing the server with sth like index = '_id'
    allowed_query_indices = {
        QUERY_TYPE_GENOME: {'type', 'contig', 'source', 'info.biosample', 'info.targets', 'info.variant_tags', 'info.source', 'info.patient_barcodes'},
        QUERY_TYPE_INFO: {'type', 'source', 'name', 'info.biosample', 'info.targets', 'info.types', 'info.assay', 'info.outtype', 'info.variant_tags', 'info.filenames'},
        QUERY_TYPE_EDGE: {'type', 'source', 'info.biosample'}
    }
    if index not in allowed_query_indices[query['type']]:
        return abort(404, f"Query of {index} is not allowed for {query['type']}")
    query = HashableDict(query)
    result = get_query_distinct_values(query, index)
    print("/distinct_values/%s for query %s returns %d results. " % (index, query, len(result)), get_query_distinct_values.cache_info())
    return json.dumps(result)

@threadsafe_lru(maxsize=8192)
def get_query_distinct_values(query, index):
    qt = QueryTree(query)
    result = set(qt.distinct(index))
    result.discard(None)
    return list(result)



#*******************************
#*         /details            *
#*******************************
from sirius.core.detail_relations import node_relations, edge_relations
from sirius.mongo import userdb
@app.route("/details/<string:data_id>")
@requires_auth
def get_details(data_id):
    if not data_id: return abort(404, 'data_id missing')
    relations = []
    if 'userFileID' in request.args:
        userFileID = request.args['userFileID']
        data = userdb.get_collection(userFileID).find_one({'_id': data_id})
        if not data:
            return abort(404, f'data with _id {data_id} not found')
    else:
        data = get_data_with_id(data_id)
        if not data:
            return abort(404, f'data with _id {data_id} not found')
        if data_id[0] == 'G' or data_id[0] == 'I':
            relations = node_relations(data_id)
        elif data_id[0] == 'E':
            relations = edge_relations(data)
        else:
            print(f"Invalid data_id {data_id}, ID should start with G, I or E")
    result = {'details': data, 'relations': relations}
    return json.dumps(result)

#**************************
#*       /suggestions     *
#**************************
from sirius.core.searchindex import get_suggestions

@app.route('/suggestions', methods=['POST'])
@requires_auth
def suggestions():
    """ Returns results for a query, with only basic information, useful for search """
    query_json = request.get_json()
    if not query_json or not "term_type" in query_json:
        return abort(500, 'no term_type')
    if not query_json or not "search_text" in query_json:
        return abort(500, 'no search_text')
    max_results = int(query_json.get('max_results', 100))
    results = {
        "results": get_suggestions(query_json["term_type"], query_json["search_text"], max_results)
    }
    print(query_json)
    print(results['results'])
    return json.dumps(results)

#**************************
#*       /query           *
#**************************
from sirius.core.query_endpoint import get_query_full_results, get_query_basic_results, get_query_gwas_results


@app.route('/query/full', methods=['POST'])
@requires_auth
def query_full():
    """ Returns results for a query, with only basic information, useful for search """
    t0 = time.time()
    result_start = request.args.get('result_start', default=None)
    result_end = request.args.get('result_end', default=None)
    query = request.get_json()
    if not query:
        return abort(404, 'no query posted')
    result_start = int(result_start) if result_start != None else 0
    if result_start < 0:
        return abort(404, 'result_start should >= 0')
    if result_end != None:
        result_end = int(result_end)
        if result_end <= result_start:
            return abort(404, 'result_end should > result_start')
    results_cache = get_query_full_results(HashableDict(query))
    results = results_cache[result_start:result_end]
    t1 = time.time()
    print(f"{len(results)} results from full query {query} cache_info: {get_query_full_results.cache_info()} {t1-t0:.1f} s")
    result_end = result_start + len(results)
    reached_end = False
    if results_cache.load_finished and result_end >= len(results_cache.loaded_data):
        reached_end = True
    return_dict = {
        "result_start": result_start,
        "result_end": result_end,
        "reached_end": reached_end,
        "data": results,
        "query": query
    }
    return json.dumps(return_dict)

@app.route('/query/basic', methods=['POST'])
@requires_auth
def query_basic():
    """ Returns results for a query, with only basic information, useful for search """
    t0 = time.time()
    result_start = request.args.get('result_start', default=None)
    result_end = request.args.get('result_end', default=None)
    query = request.get_json()
    if not query:
        return abort(404, 'no query posted')
    result_start = int(result_start) if result_start != None else 0
    if result_start < 0:
        return abort(404, 'result_start should >= 0')
    if result_end != None:
        result_end = int(result_end)
        if result_end <= result_start:
            return abort(404, 'result_end should > result_start')
    results_cache = get_query_basic_results(HashableDict(query))
    results = results_cache[result_start:result_end]
    t1 = time.time()
    print(f"{len(results)} results from basic query {query} cache_info: {get_query_full_results.cache_info()} {t1-t0:.1f} s")
    result_end = result_start + len(results)
    reached_end = False
    if results_cache.load_finished and result_end >= len(results_cache.loaded_data):
        reached_end = True
    return_dict = {
        "result_start": result_start,
        "result_end": result_end,
        "reached_end": reached_end,
        "data": results,
        "query": query
    }
    return json.dumps(return_dict)

@app.route('/query/gwas', methods=['POST'])
@requires_auth
def query_gwas():
    """ /query/gwas endpoint is specially created for sorting the GWAS SNPs by p-values """
    t0 = time.time()
    result_start = request.args.get('result_start', default=None)
    result_end = request.args.get('result_end', default=None)
    query = request.get_json()
    if not query:
        return abort(404, 'no query posted')
    result_start = int(result_start) if result_start != None else 0
    if result_start < 0:
        return abort(404, 'result_start should >= 0')
    if result_end != None:
        result_end = int(result_end)
        if result_end <= result_start:
            return abort(404, 'result_end should > result_start')
    results_cache = get_query_gwas_results(HashableDict(query))
    results = results_cache[result_start:result_end]
    t1 = time.time()
    print(f"{len(results)} results from GWAS query {query} cache_info: {get_query_gwas_results.cache_info()} {t1-t0:.1f} s")
    result_end = result_start + len(results)
    reached_end = (len(results_cache) == result_end + 1)
    return_dict = {
        "result_start": result_start,
        "result_end": result_end,
        "reached_end": reached_end,
        "data": results,
        "query": query
    }
    return json.dumps(return_dict)



#**************************
#*       /reference       *
#**************************
from sirius.core.reference_track import get_reference_gene_data, get_reference_hierarchy_data

@app.route("/reference/<string:contig>/<int:start_bp>/<int:end_bp>", methods=['GET'])
@requires_auth
def reference_annotation_track(contig, start_bp, end_bp):
    include_transcript = bool(request.args.get('include_transcript', default=False))
    # get data from cache
    if include_transcript == True:
        data = get_reference_hierarchy_data(contig)
    else:
        data = get_reference_gene_data(contig)
    # filter the ones out of range
    result_data = [g for g in data if g['start'] <= end_bp and g['start'] + g['length'] >= start_bp]
    if len(result_data) > 0:
        start_bp = min(start_bp, result_data[0]['start'])
        end_bp = max(end_bp, result_data[-1]['start'] + result_data[-1]['length'] - 1)
    result = {
        'contig': contig,
        'start_bp': start_bp,
        'end_bp': end_bp,
        'data': result_data
    }
    return json.dumps(result)



# this is a special endpoint for the "all variants" track
# it might needs to be optimized later with the help of TileDB
#*****************************
#*   /all variant_track_data     *
#*****************************
from sirius.core.all_variant_track import get_all_variants_in_range

@app.route('/all_variant_track_data/<string:contig>/<int:start_bp>/<int:end_bp>', methods=['GET'])
@requires_auth
def get_all_variant_track_data(contig, start_bp, end_bp):
    t0 = time.time()
    if contig not in loaded_contig_info_dict:
        return abort(404, 'contig not found')
    empty_return = json.dumps({
        'contig': contig,
        'start_bp': start_bp,
        'end_bp': end_bp,
        'data': []
    })
    total_length = loaded_contig_info_dict[contig]['length']
    # check start_bp and end_bp
    if start_bp > total_length or end_bp < 1 or start_bp > end_bp:
        return empty_return
    start_bp = max(start_bp, 1)
    end_bp = min(end_bp, total_length)
    result_data = get_all_variants_in_range(contig, start_bp, end_bp)
    result = {
        'contig': contig,
        'start_bp': start_bp,
        'end_bp': end_bp,
        'data': result_data
    }
    t1 = time.time()
    print(f'{len(result_data)} all_variant_data, {get_all_variants_in_range.cache_info()}; {t1-t0:.2f} s')
    return json.dumps(result)


#******************************
#*   /interval_track_data     *
#******************************
from sirius.core.interval_track import get_intervals_in_range

@app.route('/interval_track_data/<string:contig>/<int:start_bp>/<int:end_bp>', methods=['POST'])
@requires_auth
def get_interval_track_data(contig, start_bp, end_bp):
    t0 = time.time()
    query = request.get_json()
    if not query:
        return abort(404, 'no query specified')
    if contig not in loaded_contig_info_dict:
        return abort(404, 'contig not found')
    empty_return = json.dumps({
        'contig': contig,
        'start_bp': start_bp,
        'end_bp': end_bp,
        'data': []
    })
    total_length = loaded_contig_info_dict[contig]['length']
    # check start_bp and end_bp
    if start_bp > total_length or end_bp < 1 or start_bp > end_bp:
        print("interval out of range!")
        return empty_return
    start_bp = max(start_bp, 1)
    end_bp = min(end_bp, total_length)
    t1 = time.time()
    result_data = get_intervals_in_range(contig, start_bp, end_bp, query)
    result = {
        'contig': contig,
        'start_bp': start_bp,
        'end_bp': end_bp,
        'data': result_data
    }
    t2 = time.time()
    print(f'{len(result_data)} interval_data, {query}, parse {t1-t0:.2f} s | load {t2-t1:.2f} s')
    return json.dumps(result)

#******************************
#*   /variant_track_data     *
#******************************
from sirius.core.variant_track import get_variants_in_range

@app.route('/variant_track_data/<string:contig>/<int:start_bp>/<int:end_bp>', methods=['POST'])
@requires_auth
def get_variant_track_data(contig, start_bp, end_bp):
    t0 = time.time()
    query = request.get_json()
    if not query:
        return abort(404, 'no query specified')
    if contig not in loaded_contig_info_dict:
        return abort(404, 'contig not found')
    empty_return = json.dumps({
        'contig': contig,
        'start_bp': start_bp,
        'end_bp': end_bp,
        'data': []
    })
    total_length = loaded_contig_info_dict[contig]['length']
    # check start_bp and end_bp
    if start_bp > total_length or end_bp < 1 or start_bp > end_bp:
        print("interval out of range!")
        return empty_return
    start_bp = max(start_bp, 1)
    end_bp = min(end_bp, total_length)
    t1 = time.time()
    result_data = get_variants_in_range(contig, start_bp, end_bp, query)
    result = {
        'contig': contig,
        'start_bp': start_bp,
        'end_bp': end_bp,
        'data': result_data
    }
    t2 = time.time()
    print(f'{len(result_data)} variants_data, {query}, parse {t1-t0:.2f} s | load {t2-t1:.2f} s')
    return json.dumps(result)


#**************************************
#*       /user_files REST API         *
#**************************************
from sirius.core.user_files import upload_user_file, get_user_files_info, delete_user_file

@app.route('/user_files', methods=['POST','GET','DELETE'])
@requires_auth
def user_file_api():
    # upload file with POST method
    if request.method == 'POST':
        if 'file' not in request.files:
            return abort(404, "No file part")
        if 'fileType' not in request.form:
            return abort(404, "No fileType part")
        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            return abort(404, "No selected file")
        file_type = request.form['fileType']
        ret = upload_user_file(file_type, uploaded_file)
    elif request.method == 'GET':
        # get file info for current user
        ret = get_user_files_info()
    elif request.method == 'DELETE':
        # delete file from current user
        fileID = request.args.get('fileID', None)
        if fileID is None:
            return abort(404, "fileID not specified")
        ret = delete_user_file(fileID)
    return json.dumps(ret)

#**************************************
#*       /export_query API            *
#**************************************
from sirius.helpers import storage_buckets

@app.route('/export_query', methods=['POST'])
@requires_auth
def export_query():
    """ run a query then export the result """
    # get input and check valid
    jsondata = request.get_json()
    query = jsondata.get('query', None)
    file_format = jsondata.get('fileFormat', 'bed')
    upload_url = jsondata.get('uploadUrl',None)
    if not query:
        return abort(404, 'query field not found in jsondata')
    if not upload_url:
        return abort(404, 'uploadUrl field not found in jsondata')
    # export as bed
    if file_format == 'bed':
        if query['type'] != QUERY_TYPE_GENOME:
            return abort(404, 'only genome query can export as bed file')
        qt = QueryTree(query)
        bed = qt.head.convert_results_to_Bed()
        try:
            bucket = storage_buckets['canis']
            blob = bucket.blob(upload_url)
            blob.upload_from_filename(bed.fn)
        except Exception as e:
            return abort(404, f'Export failed with error:\n{e}')
    elif file_format == 'bed.gz':
        if query['type'] != QUERY_TYPE_GENOME:
            return abort(404, 'only genome query can export as bed file')
        qt = QueryTree(query)
        bed = qt.head.convert_results_to_Bed()
        # compress bed file into bed.gz using bgzip
        bedgzfn = bed.fn + '.gz'
        subprocess.run(f'/opt/giggle/lib/htslib/bgzip {bed.fn}', shell=True, check=True)
        try:
            bucket = storage_buckets['canis']
            blob = bucket.blob(upload_url)
            blob.upload_from_filename(bedgzfn)
        except Exception as e:
            return abort(404, f'Export failed with error:\n{e}')
    else:
        return abort(404, f'fileFormat {file_format} not implemented')
    return json.dumps("Success")


#**************************************
#*       /canis_api API               *
#**************************************
@app.route('/canis_api', methods=['GET'])
@requires_auth
def canis_ip_port():
    """ Useful api to provide CANIS backend ip and port to frontend """
    # if os.environ.get('VALIS_DEV_MODE', None):
    #     canis_host = os.environ.get('CANIS_DEV_SERVICE_HOST', None)
    #     canis_port = os.environ.get('CANIS_DEV_SERVICE_PORT', None)
    # else:
    #     canis_host = os.environ.get('CANIS_PROD_SERVICE_HOST', None)
    #     canis_port = os.environ.get('CANIS_PROD_SERVICE_PORT', None)
    # if canis_host == None or canis_port == None:
    #     return abort(404, 'CANIS service not found')
    # QYD: The internal IP address will not be accessible by the frontend, so
    # we return a hard-coded public IP for now
    canis_host = '35.185.236.30'
    canis_port = '80'
    return f'http://{canis_host}:{canis_port}'