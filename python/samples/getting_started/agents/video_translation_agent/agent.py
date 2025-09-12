
import os
import logging
import asyncio
import requests
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from agent_framework import ChatAgent
from agent_framework.azure import AzureResponsesClient
from video_translation_client import VideoTranslationClient
from video_translation_enum import VoiceKind

# Tool: Download video from public URL and upload to Azure Blob Storage
def download_and_upload_video(public_url: str, local_filename: str = None) -> str:
	"""
	Downloads a video from a public URL and uploads it to Azure Blob Storage.
	Returns the Azure blob URL.
	"""
	logger = logging.getLogger("video_translation_agent")
	if not local_filename:
		local_filename = os.path.basename(public_url)
	try:
		logger.info(f"Downloading video from {public_url}...")
		response = requests.get(public_url, stream=True)
		response.raise_for_status()
		with open(local_filename, "wb") as f:
			for chunk in response.iter_content(chunk_size=8192):
				f.write(chunk)
		logger.info(f"Downloaded video to {local_filename}")
		blob_url = upload_video_to_blob(local_filename)
		logger.info(f"Uploaded video to Azure Blob Storage: {blob_url}")
		os.remove(local_filename)
		return blob_url
	except Exception as e:
		logger.exception(f"Error downloading/uploading video: {str(e)}")
		return f"Error downloading/uploading video: {str(e)}"

# Tool: Upload video to Azure Blob Storage
def upload_video_to_blob(local_file_path: str) -> str:
	"""
	Uploads a local video file to Azure Blob Storage and returns the blob URL.
	Requires AZURE_STORAGE_ACCOUNT_NAME and AZURE_STORAGE_CONTAINER_NAME in env. Uses Azure AD authentication.
	"""
	logger = logging.getLogger("video_translation_agent")
	account_name = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
	container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")
	if not account_name or not container_name:
		logger.error("Missing Azure Storage configuration in environment variables.")
		return "Missing Azure Storage configuration in environment variables."
	try:
		credential = DefaultAzureCredential()
		blob_service_client = BlobServiceClient(
			f"https://{account_name}.blob.core.windows.net",
			credential=credential
		)
		blob_name = os.path.basename(local_file_path)
		blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
		with open(local_file_path, "rb") as data:
			blob_client.upload_blob(data, overwrite=True)
		blob_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
		logger.info(f"Uploaded video to blob: {blob_url}")
		return blob_url
	except Exception as e:
		logger.exception(f"Error uploading video: {str(e)}")
		return f"Error uploading video: {str(e)}"


# Tool: Translate video
def translate_video(video_url: str, target_language: str) -> str:
	"""
	Translates a video to the target language using VideoTranslationClient.
	Note: target_language must be a full locale code (e.g., 'fr-FR', 'en-US', 'es-ES').
	"""
	logger = logging.getLogger("video_translation_agent")
	logger.info(f"Starting video translation: url={video_url}, target_language={target_language}")
	source_locale = "en-US"
	voice_kind = VoiceKind.PlatformVoice
	client = VideoTranslationClient()
	try:
		logger.debug("Calling create_translate_and_run_first_iteration_until_terminated...")
		success, error, translation, iteration, translation_info, iteration_info = client.create_translate_and_run_first_iteration_until_terminated(
			video_file_url=video_url,
			source_locale=source_locale,
			target_locale=target_language,
			voice_kind=voice_kind,
		)
		if success:
			logger.info(f"Translation successful! Translation ID: {translation.id}, Iteration ID: {iteration.id}")
			logger.debug(f"Translation info: {translation_info}")
			logger.debug(f"Iteration info: {iteration_info}")
			return f"Translation successful! Translation ID: {translation.id} | Iteration ID: {iteration.id}"
		else:
			logger.error(f"Translation failed: {error}")
			return f"Translation failed: {error}"
	except Exception as e:
		logger.exception(f"Error during translation: {str(e)}")
		return f"Error during translation: {str(e)}"

# Tool: List translations
def list_translations() -> str:
	logger = logging.getLogger("video_translation_agent")
	client = VideoTranslationClient()
	try:
		logger.info("Listing all translations...")
		success, error, paged = client.request_list_translations()
		if success:
			translations = paged.value if hasattr(paged, 'value') else paged[0]['value']
			return f"Translations: {[t.id for t in translations]}"
		else:
			logger.error(f"Failed to list translations: {error}")
			return f"Failed to list translations: {error}"
	except Exception as e:
		logger.exception(f"Error listing translations: {str(e)}")
		return f"Error listing translations: {str(e)}"

# Tool: Get translation details
def get_translation_details(translation_id: str) -> str:
	logger = logging.getLogger("video_translation_agent")
	client = VideoTranslationClient()
	try:
		logger.info(f"Getting details for translation: {translation_id}")
		success, error, translation = client.request_get_translation(translation_id)
		if success and translation:
			return f"Translation details: {translation}"
		else:
			logger.error(f"Failed to get translation details: {error}")
			return f"Failed to get translation details: {error}"
	except Exception as e:
		logger.exception(f"Error getting translation details: {str(e)}")
		return f"Error getting translation details: {str(e)}"

# Tool: Delete translation
def delete_translation(translation_id: str) -> str:
	logger = logging.getLogger("video_translation_agent")
	client = VideoTranslationClient()
	try:
		logger.info(f"Deleting translation: {translation_id}")
		success, error = client.request_delete_translation(translation_id)
		if success:
			return f"Translation {translation_id} deleted successfully."
		else:
			logger.error(f"Failed to delete translation: {error}")
			return f"Failed to delete translation: {error}"
	except Exception as e:
		logger.exception(f"Error deleting translation: {str(e)}")
		return f"Error deleting translation: {str(e)}"

# Tool: List iterations for a translation
def list_iterations(translation_id: str) -> str:
	logger = logging.getLogger("video_translation_agent")
	client = VideoTranslationClient()
	try:
		logger.info(f"Listing iterations for translation: {translation_id}")
		success, error, paged = client.request_list_iterations()
		if success:
			iterations = paged.value if hasattr(paged, 'value') else paged[0]['value']
			return f"Iterations: {[i.id for i in iterations]}"
		else:
			logger.error(f"Failed to list iterations: {error}")
			return f"Failed to list iterations: {error}"
	except Exception as e:
		logger.exception(f"Error listing iterations: {str(e)}")
		return f"Error listing iterations: {str(e)}"

def main():
	# Set up logging
	logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

	# Load environment variables
	env_path = os.path.join(os.path.dirname(__file__), "openai.env")
	load_dotenv(env_path)

	endpoint = os.getenv("AZURE_AI_AGENT_ENDPOINT")
	deployment_name = os.getenv("OPENAI_CHAT_MODEL_ID", "gpt-4")
	if not endpoint:
		logging.error("Missing AZURE_AI_AGENT_ENDPOINT in environment variables.")
		raise ValueError("Missing AZURE_AI_AGENT_ENDPOINT in environment variables.")

	# Azure AD authentication
	credential = DefaultAzureCredential()
	token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")

	# Create the responses client
	chat_client = AzureResponsesClient(
		endpoint=endpoint,
		deployment_name=deployment_name,
		ad_token_provider=token_provider
	)

	# Create the agent with all video translation tools
	agent = ChatAgent(
		chat_client=chat_client,
		   instructions=(
			   "You are a helpful assistant for Azure Video Translation. "
			   "If you have a local video file, first upload it to Azure Blob Storage using the upload_video_to_blob tool, then use the resulting blob URL for translation. "
			   "If you have a publicly accessible video URL, you can use it directly with the translate_video tool. "
			   "When translating videos, always use the full locale code for languages (e.g., 'fr-FR' for French, 'en-US' for English, 'es-ES' for Spanish). "
			   "You can upload videos, translate videos, list translations, get details, delete translations, and list iterations."
		   ),
		   tools=[
			   upload_video_to_blob,
			   download_and_upload_video,
			   translate_video,
			   list_translations,
			   get_translation_details,
			   delete_translation,
			   list_iterations
		   ]
	)

	# Run the agent with a natural language query
	query = "Translate this video \"https://kchandistorage.blob.core.windows.net/videos/en-US-TryoutOriginalTTSIntro.mp4%20(1).mp4?sp=r&st=2025-09-12T22:31:35Z&se=2025-09-13T06:46:35Z&skoid=f742ec34-98c1-4a09-800c-fe1ce6fc1e33&sktid=72f988bf-86f1-41af-91ab-2d7cd011db47&skt=2025-09-12T22:31:35Z&ske=2025-09-13T06:46:35Z&sks=b&skv=2024-11-04&spr=https&sv=2024-11-04&sr=b&sig=1VNyUh00q8XYp6ucR09WQ839B38jjXbVA8m5zcojuwk%3D\" to French."
	logging.info(f"Running agent with query: {query}")
	result = asyncio.run(agent.run(query))
	logging.info(f"Agent response: {result}")
	print(f"Agent response: {result}")

if __name__ == "__main__":
	main()

