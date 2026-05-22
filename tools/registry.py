import inspect

from pydantic import BaseModel


TOOL_REGISTRY = {}


def register_tool(func):
    signature = inspect.signature(func)
    params = list(signature.parameters.values())

    if len(params) != 1:
        raise TypeError(f"{func.__name__}: tool must receive exactly one parameter.")

    param_annotation = params[0].annotation

    if not isinstance(param_annotation, type) or not issubclass(param_annotation, BaseModel):
        raise TypeError(
            f"{func.__name__}: tool parameter must be a Pydantic BaseModel."
        )

    description = (func.__doc__ or "").strip()

    if not description:
        raise ValueError(f"{func.__name__}: docstring is required.")

    TOOL_REGISTRY[func.__name__] = {
        "func": func,
        "params_model": param_annotation,
        "description": description,
    }

    return func