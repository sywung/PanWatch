FROM python:3.12-slim

RUN python -c "import pathlib, tarfile, urllib.request; archive='/tmp/dotnet-runtime.tar.gz'; urllib.request.urlretrieve('https://aka.ms/dotnet/8.0/dotnet-runtime-linux-x64.tar.gz', archive); pathlib.Path('/opt/dotnet').mkdir(parents=True, exist_ok=True); tarfile.open(archive, 'r:gz').extractall('/opt/dotnet', filter='data'); pathlib.Path(archive).unlink()"
RUN pip install --no-cache-dir pythonnet==3.0.5 fastapi uvicorn

ENV DOTNET_ROOT=/opt/dotnet \
    DOTNET_EnableWriteXorExecute=0 \
    DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=1

WORKDIR /app
COPY client.py dotnet_adapter.py app.py ./

EXPOSE 2885

CMD ["python", "-u", "app.py"]
