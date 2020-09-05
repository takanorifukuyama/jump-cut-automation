import os
import shutil
import boto3
from aws_lambda_powertools.logging import Logger
from botocore.exceptions import ClientError

INPUT_BUCKET = os.getenv("S3_INPUT_BUCKET_NAME")
OUTPUT_BUCKET = os.getenv("S3_OUTPUT_BUCKET_NAME")
DIRECTORY = "/mnt/lambda"

s3 = boto3.resource("s3")
logger = Logger()


def download_movie(event, context):
    """
    元となる動画ファイル、および書き起こしデータを
    S3 から EFS へダウンロードする関数

    Parameter
    ----------
    - event: Step Functions からの入力
        - job_name: Step Functions の実行名
        - file_name: S3 にアップロードされた動画のファイル名
    - context: Lambda 関数の実行コンテキスト

    Return
    ----------
    None

    """

    logger.info({"event": event})
    job_name = event["job_name"]
    file_name = event["file_name"]

    input_dir = f"{DIRECTORY}/{job_name}/input"
    clipped_dir = f"{DIRECTORY}/{job_name}/clipped"
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(clipped_dir, exist_ok=True)

    transcription_file_name = f"{job_name}.json"
    try:
        s3.Bucket(INPUT_BUCKET).download_file(
            file_name, f"{input_dir}/{file_name}"
        )
        s3.Bucket(OUTPUT_BUCKET).download_file(
            transcription_file_name, f"{input_dir}/transcription.json"
        )
        s3.Object(OUTPUT_BUCKET, transcription_file_name).delete()
    except ClientError as e:
        logger.error({"error": e})
        raise

    return


def upload_movie(event, context):
    """
    完成した動画を S3 へアップロードする関数

    Parameter
    ----------
    - event: Step Functions からの入力
        - job_name: Step Functions の実行名
        - file_name: S3 にアップロードされた動画のファイル名
    - context: Lambda 関数の実行コンテキスト

    Return
    ----------
    None

    """

    job_name = event["job_name"]
    file_name = event["file_name"]

    output_dir = f"{DIRECTORY}/{job_name}/output"
    try:
        s3.Bucket(OUTPUT_BUCKET).upload_file(
            f"{output_dir}/{file_name}", file_name
        )
    except ClientError as e:
        logger.error({"error": e})
        raise

    shutil.rmtree(f"{DIRECTORY}/{job_name}", ignore_errors=True)
    return
