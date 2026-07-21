from enum import StrEnum


class ProjectState(StrEnum):
    PROCESSING = "processing"
    READY_FOR_EDIT = "ready_for_edit"
    EDITING = "editing"
    REVIEWED = "reviewed"
    EXPORTING = "exporting"
    EXPORT_SUCCEEDED = "export_succeeded"
    PROCESSING_FAILED = "processing_failed"
    EXPORT_FAILED = "export_failed"
    UNSUPPORTED_INPUT = "unsupported_input"


ALLOWED = {
    ProjectState.PROCESSING: {
        ProjectState.READY_FOR_EDIT,
        ProjectState.PROCESSING_FAILED,
        ProjectState.UNSUPPORTED_INPUT,
    },
    ProjectState.READY_FOR_EDIT: {ProjectState.EDITING},
    ProjectState.EDITING: {ProjectState.REVIEWED},
    ProjectState.REVIEWED: {ProjectState.EXPORTING},
    ProjectState.EXPORTING: {
        ProjectState.EXPORT_SUCCEEDED,
        ProjectState.EXPORT_FAILED,
    },
    ProjectState.EXPORT_FAILED: {ProjectState.EXPORTING},
}


class InvalidTransition(ValueError):
    pass


def transition(current: ProjectState, target: ProjectState) -> ProjectState:
    if target not in ALLOWED.get(current, set()):
        raise InvalidTransition(f"{current} -> {target} is not allowed")
    return target
