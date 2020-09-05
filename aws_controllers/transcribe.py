import boto3
import os
from aws_lambda_powertools.logging import Logger
from botocore.exceptions import ClientError

REGION = os.getenv("REGION")
INPUT_BUCKET = os.getenv("S3_INPUT_BUCKET_NAME")
OUTPUT_BUCKET = os.getenv("S3_OUTPUT_BUCKET_NAME")
DIRECTORY = "/mnt/lambda"
MOVIE_FORMAT = "mp4"
LANGUAGE_CODE = "ja-JP"

transcribe = boto3.client("transcribe")
s3 = boto3.resource("s3")
logger = Logger()


def start_job(event, context):
    """
    Step Functions の Input から Transcribe の書き起こしジョブを起動し、
    動画の音声ファイルの書き起こしを行う関数

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
    movie_url = f"https://{INPUT_BUCKET}.s3-{REGION}.amazonaws.com/{file_name}"

    try:
        response = transcribe.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={"MediaFileUri": movie_url},
            MediaFormat=MOVIE_FORMAT,
            LanguageCode=LANGUAGE_CODE,
            OutputBucketName=OUTPUT_BUCKET,
        )
        logger.info({"response": response})
    except ClientError as e:
        logger.error({"error": e})
        raise

    return
