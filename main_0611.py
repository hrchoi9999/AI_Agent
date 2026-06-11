
from dotenv import load_dotenv
# .env 파일 안의 OPENAI_API_KEY 읽기
load_dotenv()

import os
import tempfile
import streamlit as st

# ChromaDB's OpenTelemetry dependency can hit protobuf compatibility issues
# on Streamlit Cloud Python 3.14. Set this before importing Chroma.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

# PDF Loader
from langchain_community.document_loaders import PyPDFLoader

# 문서 Splitter
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Chroma Vector DB
from langchain_chroma import Chroma


# Gemini 모델
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

# Prompt
from langchain_core.prompts import (  ChatPromptTemplate )
from langchain_core.runnables import RunnablePassthrough

st.title("PDF File Reader")
st.write("----------------")

uploaded_file = st.file_uploader(   "PDF 파일을 선택하세요",    type=["pdf"] )
st.write("----------------")


def load_gemini_api_key():
    if os.getenv("GEMINI_API_KEY"):
        os.environ.setdefault("GOOGLE_API_KEY", os.getenv("GEMINI_API_KEY", ""))
        return True

    try:
        api_key = st.secrets.get("GEMINI_API_KEY")
    except Exception:
        api_key = None

    if api_key:
        os.environ["GEMINI_API_KEY"] = str(api_key)
        os.environ["GOOGLE_API_KEY"] = str(api_key)
        return True

    return False


def pdf_to_document(uploaded_file):
    temp_dir = tempfile.TemporaryDirectory()

    temp_filepath = os.path.join( temp_dir.name,  uploaded_file.name    )

    with open(   temp_filepath,    "wb"   ) as f:
        f.write(  uploaded_file.getvalue()   )

    loader = PyPDFLoader(    temp_filepath   )
    pages = loader.load()
    return pages


def format_documents(documents):
    context_parts = []
    for index, document in enumerate(documents, start=1):
        page = document.metadata.get("page")
        page_label = f"{page + 1}페이지" if isinstance(page, int) else "페이지 정보 없음"
        context_parts.append(f"[문서 {index} / {page_label}]\n{document.page_content}")
    return "\n\n".join(context_parts)

if uploaded_file is not None:
    if not load_gemini_api_key():
        st.error("GEMINI_API_KEY가 설정되어 있지 않습니다. Streamlit Cloud의 App settings > Secrets에 GEMINI_API_KEY를 등록해 주세요.")
        st.stop()

    pages = pdf_to_document(  uploaded_file   )
    st.success(  f"PDF 로딩 완료 : {len(pages)} 페이지"   )

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )

    texts = text_splitter.split_documents( pages  )
    st.info( f"분할된 문서 개수 : {len(texts)}"    )

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004"
    )



    db = Chroma.from_documents(

        documents=texts,

        embedding=embeddings

    )


    retriever = db.as_retriever(

        search_kwargs={
            "k":3
        }

    )




    st.header(
        "PDF에게 질문하세요"
    )


    question = st.text_input(
        "질문 입력"
    )




    if st.button(
        "질문하기"
    ):



        if question:



            with st.spinner(
                "답변 생성 중..."
            ):



                llm = ChatGoogleGenerativeAI(

                    model="gemini-2.5-flash",

                    temperature=0

                )


                prompt = ChatPromptTemplate.from_template(
                    """
                    당신은 PDF 분석 전문가입니다.

                    아래 Context만 이용해서
                    질문에 답하세요.

                    Context:
                    {context}

                    질문:
                    {input}

                    답변:
                    """
                )


                qa_chain = (
                    {
                        "context": retriever | format_documents,
                        "input": RunnablePassthrough(),
                    }
                    | prompt
                    | llm
                )

                response = qa_chain.invoke(question)



                # 답변 출력

                st.write(
                    response.content
                )



        else:

            st.warning(
                "질문을 입력하세요."
            )
