import boto3
import json
import os
import subprocess
from aws_lambda_powertools.logging import Logger
from botocore.exceptions import ClientError

OUTPUT_BUCKET = os.getenv("S3_OUTPUT_BUCKET_NAME")
TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME")
DIRECTORY = "/mnt/lambda"

s3 = boto3.resource("s3")
dynamo = boto3.resource("dynamodb")
table = dynamo.Table(TABLE_NAME)
logger = Logger()


class MovieFormatError(Exception):
    pass


class MovieClippingError(MovieFormatError):
    pass


class MovieConcatError(MovieFormatError):
    pass


def clip_speech(event, context):
    """
    SQS でカットの対象となる発話区間を含んだメッセージを受信すると、
    その区間にもとづき、動画のカットを行う関数
    正常に完了した場合、DynamoDB から該当するレコードを削除する

    Parameter
    ----------
    - event: SQS から受信したメッセージ
        - Records: 受信したメッセージの配列
            - job_name: Step Functions の実行名
            - index: 何番目の発話区間かを表すインデックス
    - context: Lambda 関数の実行コンテキスト

    Return
    ----------
    None

    """

    def spawn_clip_process(start_time, duration, input, output):
        """
        動画のカットを行い EFS 上に保存するプロセス (ffmpeg) を立ち上げる関数

        Parameter
        ----------
        - start_time: 発話区間の開始時間
        - duration: 発話区間の長さ
        - input: カットの対象となる動画ファイルのパス
        - output: カットした動画ファイルを配置するパス

        Return
        ----------
        - is_success: プロセスの実行が成功したかどうかを表すフラグ

        """

        cmd = [
            "./ffmpeg",
            "-y",
            "-ss",
            str(start_time),
            "-i",
            input,
            "-t",
            str(duration),
            output,
        ]
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout = result.stdout.decode("utf8")
        stderr = result.stderr.decode("utf8")
        if len(stdout) != 0:
            logger.info({"ffmpeg_stdout": stdout})
        if len(stderr) != 0:
            logger.info({"ffmpeg_stderr": stderr})

        is_success = True
        if result.returncode != 0:
            is_success = False
        return is_success

    logger.info({"event": event})

    messages = event["Records"]
    for message in messages:
        message_body = json.loads(message["body"])
        job_name = message_body["job_name"]
        index = message_body["index"]

        try:
            record = table.get_item(Key={"job_name": job_name, "index": index})
        except ClientError as e:
            logger.error({"error": e})
        item = record["Item"]
        logger.info({"dynamodb_item": item})

        file_name = item["file_name"]
        input_file = f"{DIRECTORY}/{job_name}/input/{file_name}"
        output_file = f"{DIRECTORY}/{job_name}/clipped/{index}.mp4"
        is_success = spawn_clip_process(
            item["start_time"], item["duration"], input_file, output_file
        )
        if is_success:
            try:
                table.delete_item(Key={"job_name": job_name, "index": index})
            except ClientError as e:
                logger.error({"error": e})
                raise
        else:
            raise MovieClippingError()

    return


def concat_speech(event, context):
    """
    カットされた動画を一つに結合し、EFS 上に保存する関数

    Parameter
    ----------
    - event: SQS から受信したメッセージ
        - job_name: Step Functions の実行名
        - file_name: S3 にアップロードされた動画のファイル名
        - file_count: 生成されたカット済み動画ファイル数
    - context: Lambda 関数の実行コンテキスト

    Return
    ----------
    None

    """

    def spawn_concat_process(file_name, file_count, clip_dir, output_dir):
        """
        動画を結合するプロセス (ffmpeg) を立ち上げる関数

        Parameter
        ----------
        - file_name: S3 にアップロードされた動画のファイル名
        - file_count: 生成されたカット済み動画ファイル数
        - clip_dir: 生成されたカット済み動画が配置されたディレクトリ
        - output_dir: 結合した動画を配置するディレクトリ

        Return
        ----------
        - is_success: プロセスの実行が成功したかどうかを表すフラグ

        """

        file_list = []
        for index in range(file_count):
            file_list += [f"file {clip_dir}/{index}.mp4"]
        with open(f"{output_dir}/concat_list", mode="w") as f:
            f.write("\n".join(file_list))

        cmd = [
            "./ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            f"{output_dir}/concat_list",
            "-c",
            "copy",
            f"{output_dir}/{file_name}",
        ]
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout = result.stdout.decode("utf8")
        stderr = result.stderr.decode("utf8")
        if len(stdout) != 0:
            logger.info({"ffmpeg_stdout": stdout})
        if len(stderr) != 0:
            logger.info({"ffmpeg_stderr": stderr})

        is_success = True
        if result.returncode != 0:
            is_success = False
        return is_success

    job_name = event["job_name"]
    file_name = event["file_name"]
    file_count = event["file_count"]

    clip_dir = f"{DIRECTORY}/{job_name}/clipped"
    output_dir = f"{DIRECTORY}/{job_name}/output"
    os.makedirs(output_dir, exist_ok=True)

    is_success = spawn_concat_process(
        file_name, file_count, clip_dir, output_dir
    )
    if is_success:
        return
    else:
        raise MovieConcatError()
