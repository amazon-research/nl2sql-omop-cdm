import logging
import psycopg2
#import boto3
import pandas as pd


def connect_to_db(redshift_parameters, user, password):
#     client = boto3.client('redshift',region_name=redshift_parameters['region'])

#     cluster_creds = client.get_cluster_credentials(DbUser=redshift_parameters['user'],
#                                                 DbName=redshift_parameters['database'],
#                                                 ClusterIdentifier=redshift_parameters['cluster_id'],
#                                                 AutoCreate=False)

    try:
        conn = psycopg2.connect(
            host=redshift_parameters['url'],
            port=redshift_parameters['port'],
#             user=cluster_creds['DbUser'],
#             password=cluster_creds['DbPassword'],            
            user=user,
            password=password,
            database=redshift_parameters['database']
        )

        return conn
    
    except psycopg2.Error:
        logger.exception('Failed to open database connection.')
        print("Failed")
    
    
def execute_query(cursor, query, limit=None):
    try:
        cursor.execute(query)
    except:
        return None
    
    columns = [c.name for c in cursor.description]
    results = cursor.fetchall()
    if limit: results = results[:limit]
    
    out = pd.DataFrame(results, columns=columns)
    
    return out


if __name__=="__main__":
    from __init__ import *
    import config
    sql_query = "SELECT COUNT(person_id) FROM cmsdesynpuf23m.person JOIN  ( SELECT concept_id FROM cmsdesynpuf23m.concept WHERE concept_name='FEMALE' AND domain_id='Gender' AND standard_concept='S' )  ON gender_concept_id=concept_id;"
    
    conn = connect_to_db(config.REDSHIFT_PARM)
    cursor = conn.cursor()
    out_df = execute_query(cursor, sql_query, limit=5)
    conn.close()
    print(out_df)