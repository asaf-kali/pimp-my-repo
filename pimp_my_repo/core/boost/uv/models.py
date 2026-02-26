from pydantic import BaseModel, ConfigDict, Field


class DependencyFiles(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    requirements_txt: bool = Field(default=False, alias="requirements.txt")
    setup_py: bool = Field(default=False, alias="setup.py")
    pyproject_toml: bool = Field(default=False, alias="pyproject.toml")
    pipfile: bool = Field(default=False, alias="Pipfile")
    poetry_lock: bool = Field(default=False, alias="poetry.lock")
    pipfile_lock: bool = Field(default=False, alias="Pipfile.lock")


class ConfigFiles(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ruff_dot_toml: bool = Field(default=False, alias=".ruff.toml")
    ruff_toml: bool = Field(default=False, alias="ruff.toml")
    mypy_ini: bool = Field(default=False, alias="mypy.ini")
    mypy_dot_ini: bool = Field(default=False, alias=".mypy.ini")
    pre_commit_config_dot_yaml: bool = Field(default=False, alias=".pre-commit-config.yaml")
    pre_commit_config_yaml: bool = Field(default=False, alias="pre-commit-config.yaml")
    justfile: bool = False
    makefile: bool = Field(default=False, alias="Makefile")
    makefile_lower: bool = Field(default=False, alias="makefile")


class DetectionResult(BaseModel):
    dependencies: DependencyFiles
    configs: ConfigFiles
