from elevator_control.adapters.outbound.persistence import models as m
from elevator_control.domain import entities as e
from elevator_control.domain.enums import (
    EventStatus,
    EventType,
    LiftStatus,
    ServiceRequestStatus,
    TechnicianStatus,
)


def lift_to_domain(row: m.LiftModel) -> e.Lift:
    return e.Lift(
        id=row.id,
        model=row.model,
        status=LiftStatus(row.status),
        location=row.location,
        is_emergency=row.is_emergency,
    )


def sensor_to_domain(row: m.SensorModel) -> e.Sensor:
    return e.Sensor(
        id=row.id,
        lift_id=row.lift_id,
        sensor_type=row.sensor_type,
        current_value=row.current_value,
        threshold_norm=row.threshold_norm,
    )


def event_to_domain(row: m.EventModel) -> e.Event:
    return e.Event(
        id=row.id,
        lift_id=row.lift_id,
        event_type=EventType(row.event_type),
        description=row.description,
        status=EventStatus(row.status),
    )


def technician_to_domain(row: m.TechnicianModel) -> e.Technician:
    return e.Technician(
        id=row.id,
        name=row.name,
        status=TechnicianStatus(row.status),
    )


def service_request_to_domain(row: m.ServiceRequestModel) -> e.ServiceRequest:
    return e.ServiceRequest(
        id=row.id,
        lift_id=row.lift_id,
        reason=row.reason,
        status=ServiceRequestStatus(row.status),
        technician_id=row.technician_id,
    )


def report_to_domain(row: m.ReportModel) -> e.Report:
    return e.Report(
        id=row.id,
        service_request_id=row.service_request_id,
        work_description=row.work_description,
        final_lift_status=LiftStatus(row.final_lift_status),
        created_at=row.created_at,
    )
