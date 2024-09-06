from base64 import b64encode

import streamlit as st
from logzero import logger

from supersullytools.llm.completions import CompletionHandler, ImagePromptMessage


def main():
    st.title("Completion Handler Testing")
    ch = CompletionHandler(logger=logger, enable_bedrock=True)
    model = st.selectbox("Model", ch.available_models, format_func=lambda x: x.llm)
    image = st.file_uploader("Image", type=["png", "jpg"])
    if chat_input := st.chat_input():
        if image:
            prompt = [
                ImagePromptMessage(
                    content=chat_input,
                    images=[b64encode(image.getvalue()).decode()],
                    image_formats=["png" if image.name.endswith("png") else "jpeg"],  # noqa
                )
            ]
        else:
            prompt = chat_input
        st.session_state.response = ch.get_completion(prompt=prompt, model=model)

    if response := st.session_state.get("response"):
        st.write(response.model_dump(mode="json"))


if __name__ == "__main__":
    main()
