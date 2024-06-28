"""
streamlit_media_manager.py

This Streamlit app provides a demo interface for managing media files stored in an Amazon S3 bucket,
with metadata stored in Amazon DynamoDB. It includes features for uploading, retrieving, generating
previews, and deleting media files, with optional gzip compression and encryption support for efficient
and secure storage of compressible data like CSV and JSON files.

Functions:
    setup_media_manager() -> MediaManager:
        Sets up and returns a MediaManager instance for managing media files.

    detect_media_type(file_name: str) -> Optional[MediaType]:
        Detects the media type of a file based on its MIME type.

    display_content(contents, media_type: MediaType):
        Displays the content in the Streamlit app based on the media type.

    upload_media_dialog():
        Handles the file upload process, including optional gzip compression and encryption, and generates previews.

    get_preview_image_base64(media_id: str) -> str:
        Retrieves the preview image for a given media ID and encodes it in base64 format.

Streamlit Sections:
    - Upload Media: Allows users to upload media files with optional gzip compression and encryption, and preview generation.
    - Recent Uploads: Displays a table of recent uploads with preview images and options to delete selected files.
    - Retrieve Metadata: Retrieves and displays the metadata for a specified media ID.
    - Retrieve Content: Retrieves and displays the content of a specified media ID, with a download option.
    - Retrieve Preview: Retrieves and displays the preview of a specified media ID.
    - Delete Media: Deletes the specified media file and its metadata from S3 and DynamoDB.

Dependencies:
    - base64: For encoding preview images in base64 format.
    - mimetypes: For detecting MIME types of files.
    - os: For accessing environment variables.
    - pandas: For creating and manipulating DataFrames.
    - streamlit: For building the web app interface.
    - logzero: For logging information and errors.
    - simplesingletable: For interacting with DynamoDB.
    - supersullytools.utils.media_manager: For managing media files and their metadata.
    - cryptography: For generating and using encryption keys (optional).

Usage:
    1. Set up the required environment variables:
        - DYNAMODB_TABLE: The name of the DynamoDB table.
        - S3_BUCKET: The name of the S3 bucket.
        - (optional) S3_MEDIA_PREFIX: A prefix within the bucket to use.

    2. Run the Streamlit app:
        streamlit run streamlit_media_manager.py

    3. Use the app interface to upload, view, retrieve, and delete media files.
"""

import base64
import mimetypes
import os
import secrets
from io import BytesIO
from typing import Optional

import pandas as pd
import streamlit as st
from logzero import logger
from simplesingletable import DynamoDbMemory

from supersullytools.utils.media_manager import MediaManager, MediaType, generate_text_image

st.set_page_config(layout="wide")


def setup_media_manager():
    # Placeholder function to set up the MediaManager
    # Replace with your actual implementation
    dynamodb_memory = DynamoDbMemory(logger=logger, table_name=os.environ.get("DYNAMODB_TABLE"))
    return MediaManager(
        bucket_name=os.environ.get("S3_BUCKET"),
        logger=logger,
        dynamodb_memory=dynamodb_memory,
        global_prefix=os.environ.get("S3_MEDIA_PREFIX") or "media-manager-testing",
    )


def detect_media_type(file_name: str) -> Optional[MediaType]:
    mime_type, _ = mimetypes.guess_type(file_name)
    if mime_type:
        if mime_type.startswith("image"):
            return MediaType.image
        elif mime_type.startswith("audio"):
            return MediaType.audio
        elif mime_type.startswith("video"):
            return MediaType.video  # Assuming "video" is a valid media type in your MediaManager
        elif mime_type == "application/pdf":
            return MediaType.pdf
        elif mime_type.startswith("text"):
            return MediaType.text
    return None


def display_content(contents, media_type: MediaType):
    if media_type == "image":
        st.image(contents, caption="Image")
    elif media_type == "audio":
        st.audio(contents)
    elif media_type == "video":
        st.video(contents)
    else:
        st.write("Unable to display contents")


# Initialize the media manager
media_manager = setup_media_manager()

st.title("Media Manager Streamlit App")

# Key generation section
st.header("Key Generation")
if st.button("Generate New Encryption Key"):
    # Generate a random secret key (AES256 needs 32 bytes)
    new_key = base64.urlsafe_b64encode(secrets.token_bytes(32))
    st.code(new_key.decode(), language="text")

# Global encryption key
encryption_key = st.text_input("Global Encryption Key (optional)", type="password", key="global_encryption_key")
if encryption_key:
    encryption_key = base64.urlsafe_b64decode(encryption_key.encode())


@st.experimental_dialog("Upload Media", width="large")
def upload_media_dialog():
    # File upload section
    st.header("Upload Media")
    uploaded_file = st.file_uploader("Choose a file")

    default_media_type = None
    if uploaded_file:
        media_types = list(MediaType)
        st.write(mimetypes.guess_type(uploaded_file.name)[0])
        try:
            default_media_type = media_types.index(detect_media_type(uploaded_file.name))
        except ValueError:
            pass

    media_type: MediaType = st.selectbox(
        "Select media type", options=list(MediaType), index=default_media_type, format_func=lambda x: x.value
    )

    if uploaded_file is not None and media_type:
        st.write("Filename:", uploaded_file.name)
        bytes_data = uploaded_file.read()
        file_obj = BytesIO(bytes_data)
        gzip_content = st.checkbox("Gzip content before storage")
        encrypt_content = st.checkbox("Encrypt content")
        encrypt_preview = st.checkbox("Encrypt preview")
        try:
            preview = media_manager.generate_preview(uploaded_file, media_type)
            st.image(preview, media_type)
        except Exception as e:
            st.error(f"Failed to generate preview for file: {str(e)}")

        if st.button("Upload"):
            try:
                metadata = media_manager.upload_new_media(
                    uploaded_file.name,
                    media_type,
                    file_obj,
                    use_gzip=gzip_content,
                    encryption_key=encryption_key if encrypt_content else "",
                    encrypt_preview=encrypt_preview,
                )
                st.experimental_rerun()

            except Exception as e:
                st.error(f"Failed to upload file: {str(e)}")
            else:
                return metadata


if st.button("Upload Media"):
    upload_media_dialog()

st.header("Recent Uploads")

data = []
previews = []


@st.cache_data(persist=True)
def get_preview_image_base64(media_id: str, encryption_key: Optional[bytes] = None) -> str:
    preview_content = media_manager.retrieve_media_preview(media_id, encryption_key=encryption_key)
    return base64.b64encode(preview_content).decode("utf-8")


@st.cache_data(ttl=15)
def list_media():
    return media_manager.list_available_media(num=50, oldest_first=False)


for media in list_media():
    if media.preview_encrypted:
        if encryption_key:
            previews.append(get_preview_image_base64(media.resource_id, encryption_key))
        else:
            previews.append(base64.b64encode(generate_text_image("Encryption Key Required")).decode("utf-8"))
    else:
        previews.append(get_preview_image_base64(media.resource_id))

    media_dict = media.model_dump(
        mode="json",
        exclude={
            "created_at",
            "updated_at",
            "file_size_bytes",
            "preview_size_bytes",
            "storage_size_bytes",
            "preview_storage_size_bytes",
        },
    )
    data.append(media_dict)


# Convert list of dictionaries to DataFrame
df = pd.DataFrame(data)

# Add a column for the preview images
df["Preview"] = [f"data:image/jpeg;base64,{preview}" for preview in previews]

# Display the DataFrame with custom column configuration
selected = st.dataframe(
    df,
    column_config={
        "Preview": st.column_config.ImageColumn(
            label="Preview Image",
            help="Preview of the uploaded media",
            width="small",
        ),
    },
    use_container_width=True,
    on_select="rerun",
    selection_mode="multi-row",
)

if work_on_rows := selected["selection"]["rows"]:
    selected_media_ids = [df.iloc[x]["resource_id"] for x in work_on_rows]
    if st.button("Delete selected", type="primary"):
        for delete_media_id in selected_media_ids:
            try:
                preview_metadata = media_manager.delete_media(delete_media_id)
                st.info(f"Deleted {delete_media_id}")
            except Exception as e:
                st.error(f"Failed to delete media: {str(e)}")

# Retrieve metadata section
st.header("Retrieve Metadata")
media_id = st.text_input("Enter media ID to retrieve metadata")
if st.button("Retrieve Metadata"):
    try:
        metadata = media_manager.retrieve_metadata(media_id)
        st.json(metadata.dict())
    except Exception as e:
        st.error(f"Failed to retrieve metadata: {str(e)}")

# Retrieve content section
st.header("Retrieve Content")
media_id_content = st.text_input("Enter media ID to retrieve content")
if st.button("Retrieve Content"):
    try:
        contents_metadata, contents = media_manager.retrieve_media_metadata_and_contents(
            media_id_content, encryption_key=encryption_key
        )
        st.write(contents_metadata.src_filename)
        display_content(contents, contents_metadata.media_type)
        st.download_button("Download Content", data=contents, file_name=contents_metadata.src_filename)
    except Exception as e:
        st.error(f"Failed to retrieve content: {str(e)}")

# Retrieve preview section
st.header("Retrieve Preview")
media_id_preview = st.text_input("Enter media ID to retrieve preview")
if st.button("Retrieve Preview"):
    try:
        preview_metadata = media_manager.retrieve_metadata(media_id_preview)
        preview_contents = media_manager.retrieve_media_preview(media_id_preview, encryption_key=encryption_key)
        st.image(preview_contents, preview_metadata.media_type)
    except Exception as e:
        st.error(f"Failed to retrieve preview: {str(e)}")

# Delete media section
st.header("Delete Media")
delete_media_id = st.text_input("Enter media ID to delete; this cannot be undone!")
if st.button("Delete Media", type="primary"):
    try:
        media_manager.delete_media(delete_media_id)
        st.info("Deleted")
    except Exception as e:
        st.error(f"Failed to delete media: {str(e)}")
