from dataclasses import dataclass

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import get_settings


@dataclass(frozen=True)
class S3ObjectRef:
    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


class S3Client:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.s3_bucket:
            raise RuntimeError("S3_BUCKET is not set")

        endpoint = settings.s3_endpoint_url or settings.s3_internal_endpoint_url
        self._bucket = settings.s3_bucket
        client_kwargs: dict[str, object] = {
            "region_name": settings.s3_region,
            "config": Config(signature_version="s3v4"),
        }
        if endpoint:
            client_kwargs["endpoint_url"] = endpoint
            client_kwargs["use_ssl"] = settings.s3_secure
        else:
            # Managed S3 should default to TLS when no custom endpoint is provided.
            client_kwargs["use_ssl"] = True

        if settings.s3_access_key_id:
            client_kwargs["aws_access_key_id"] = settings.s3_access_key_id
        if settings.s3_secret_access_key:
            client_kwargs["aws_secret_access_key"] = settings.s3_secret_access_key

        self._client = boto3.client("s3", **client_kwargs)

    @property
    def bucket(self) -> str:
        return self._bucket

    def put_bytes(self, *, key: str, data: bytes, content_type: str) -> S3ObjectRef:
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return S3ObjectRef(bucket=self._bucket, key=key)

    def get_bytes(self, *, bucket: str, key: str) -> bytes:
        response = self._client.get_object(Bucket=bucket, Key=key)
        return response["Body"].read()

    def create_presigned_put_url(
        self,
        *,
        key: str,
        content_type: str,
        expires_in_seconds: int = 300,
    ) -> str:
        return self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in_seconds,
            HttpMethod="PUT",
        )

    def create_presigned_get_url(
        self,
        *,
        bucket: str,
        key: str,
        expires_in_seconds: int = 300,
    ) -> str:
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in_seconds,
            HttpMethod="GET",
        )

    def object_exists(self, *, bucket: str, key: str) -> bool:
        try:
            self._client.head_object(Bucket=bucket, Key=key)
            return True
        except ClientError as exc:
            error_code = str(exc.response.get("Error", {}).get("Code", ""))
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
