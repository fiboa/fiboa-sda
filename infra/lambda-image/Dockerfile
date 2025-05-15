FROM public.ecr.aws/lambda/python:3.11

WORKDIR ${LAMBDA_TASK_ROOT}

COPY main.py .
RUN pip install slack-sdk==3.35.0 requests==2.32.2 tenacity==9.0.0

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD [ "main.handler" ]
