
from pathlib import Path
import dotenv
from datetime import datetime, timezone
from db_setup import SQLiteImageStore

dotenv.load_dotenv()

store: SQLiteImageStore | None = None

async def create_and_store_base64_encoded_images() -> tuple[str, str]:
    global store
    store = SQLiteImageStore()

    """Load and encode the images as base64."""
    folder = Path("./images")

    for file_path in sorted(folder.iterdir()):
        if not file_path.is_file():
            continue
        with open(file_path, "rb") as f:
            image_data = f.read()
            image_uri = f"data:image/jpeg,{image_data}"

            text_id = f"{file_path.name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
            file_name = file_path.name.split(".")[0]
            record = await store.add_image_from_base64(
                text_id=text_id,
                base64_data=image_data,
                image_name=file_name,
                description=f"{file_name} image",
                metadata={"source": "sample", "scenario": "azure_ai_chat_client"},
                tags=[file_name],
                mime_type="image/jpeg",
                image_uri=image_uri,
            )
            print(f"Stored image in SQLite with id={record.id} text_id={record.text_id}")
