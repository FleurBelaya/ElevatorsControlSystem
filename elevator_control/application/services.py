from elevator_control.domain import entities as e
from elevator_control.domain.enums import (
    EventStatus,
    EventType,
    LiftStatus,
    ServiceRequestStatus,
    TechnicianStatus,
)
from elevator_control.domain.exceptions import NotFoundError
from elevator_control.ports.outbound import repositories as r


class LiftApplicationService:
    def __init__(
        self,
        lifts: r.LiftRepository,
        sensors: r.SensorRepository,
    ) -> None:
        self._lifts = lifts
        self._sensors = sensors

    def get(self, lift_id: int) -> e.Lift:
        lift = self._lifts.get_by_id(lift_id)
        if lift is None:
            raise NotFoundError("Лифт не найден")
        return lift

    def list_page(self, skip: int, limit: int) -> tuple[list[e.Lift], int]:
        return self._lifts.list_paginated(skip, limit)

    def create(self, lift: e.Lift) -> e.Lift:
        return self._lifts.create(lift)

    def update(self, lift_id: int, **fields) -> e.Lift:
        current = self._lifts.get_by_id(lift_id)
        if current is None:
            raise NotFoundError("Лифт не найден")
        updated = e.Lift(
            id=current.id,
            model=fields.get("model", current.model),
            status=fields.get("status", current.status),
            location=fields.get("location", current.location),
            is_emergency=fields.get("is_emergency", current.is_emergency),
        )
        result = self._lifts.update(updated)
        assert result is not None
        return result

    def delete(self, lift_id: int) -> None:
        if not self._lifts.delete(lift_id):
            raise NotFoundError("Лифт не найден")


class SensorApplicationService:
    def __init__(self, lifts: r.LiftRepository, sensors: r.SensorRepository) -> None:
        self._lifts = lifts
        self._sensors = sensors

    def ensure_lift(self, lift_id: int) -> None:
        if self._lifts.get_by_id(lift_id) is None:
            raise NotFoundError("Лифт не найден")

    def list_for_lift(self, lift_id: int) -> list[e.Sensor]:
        self.ensure_lift(lift_id)
        return self._sensors.list_by_lift(lift_id)

    def get(self, sensor_id: int) -> e.Sensor:
        s = self._sensors.get_by_id(sensor_id)
        if s is None:
            raise NotFoundError("Датчик не найден")
        return s

    def create(self, sensor: e.Sensor) -> e.Sensor:
        self.ensure_lift(sensor.lift_id)
        return self._sensors.create(sensor)

    def update(self, sensor_id: int, **fields) -> e.Sensor:
        current = self._sensors.get_by_id(sensor_id)
        if current is None:
            raise NotFoundError("Датчик не найден")
        updated = e.Sensor(
            id=current.id,
            lift_id=current.lift_id,
            sensor_type=fields.get("sensor_type", current.sensor_type),
            current_value=fields.get("current_value", current.current_value),
            threshold_norm=fields.get("threshold_norm", current.threshold_norm),
        )
        result = self._sensors.update(updated)
        assert result is not None
        return result

    def delete(self, sensor_id: int) -> None:
        if not self._sensors.delete(sensor_id):
            raise NotFoundError("Датчик не найден")


class EventApplicationService:
    def __init__(
        self,
        lifts: r.LiftRepository,
        events: r.EventRepository,
    ) -> None:
        self._lifts = lifts
        self._events = events

    def get(self, event_id: int) -> e.Event:
        ev = self._events.get_by_id(event_id)
        if ev is None:
            raise NotFoundError("Событие не найдено")
        return ev

    def list_page(
        self,
        skip: int,
        limit: int,
        lift_id: int | None,
        status: EventStatus | None,
        event_type: EventType | None,
    ) -> tuple[list[e.Event], int]:
        return self._events.list_filtered(skip, limit, lift_id, status, event_type)

    def create(self, event: e.Event) -> e.Event:
        if self._lifts.get_by_id(event.lift_id) is None:
            raise NotFoundError("Лифт не найден")
        return self._events.create(event)

    def update(self, event_id: int, **fields) -> e.Event:
        current = self._events.get_by_id(event_id)
        if current is None:
            raise NotFoundError("Событие не найдено")
        updated = e.Event(
            id=current.id,
            lift_id=current.lift_id,
            event_type=fields.get("event_type", current.event_type),
            description=fields.get("description", current.description),
            status=fields.get("status", current.status),
        )
        result = self._events.update(updated)
        assert result is not None
        return result


class ServiceRequestApplicationService:
    def __init__(
        self,
        lifts: r.LiftRepository,
        technicians: r.TechnicianRepository,
        requests: r.ServiceRequestRepository,
    ) -> None:
        self._lifts = lifts
        self._technicians = technicians
        self._requests = requests

    def get(self, rid: int) -> e.ServiceRequest:
        req = self._requests.get_by_id(rid)
        if req is None:
            raise NotFoundError("Заявка не найдена")
        return req

    def list_page(
        self,
        skip: int,
        limit: int,
        lift_id: int | None,
        status: ServiceRequestStatus | None,
    ) -> tuple[list[e.ServiceRequest], int]:
        return self._requests.list_filtered(skip, limit, lift_id, status)

    def create(self, req: e.ServiceRequest) -> e.ServiceRequest:
        if self._lifts.get_by_id(req.lift_id) is None:
            raise NotFoundError("Лифт не найден")
        if req.technician_id is not None and self._technicians.get_by_id(req.technician_id) is None:
            raise NotFoundError("Техник не найден")
        status = req.status
        if req.technician_id is not None and status == ServiceRequestStatus.PENDING:
            status = ServiceRequestStatus.ASSIGNED
        to_save = e.ServiceRequest(
            id=req.id,
            lift_id=req.lift_id,
            reason=req.reason,
            status=status,
            technician_id=req.technician_id,
        )
        created = self._requests.create(to_save)
        if req.technician_id is not None:
            tech = self._technicians.get_by_id(req.technician_id)
            if tech is not None:
                self._technicians.update(
                    e.Technician(id=tech.id, name=tech.name, status=TechnicianStatus.BUSY)
                )
        return created

    def update(self, rid: int, **fields) -> e.ServiceRequest:
        current = self._requests.get_by_id(rid)
        if current is None:
            raise NotFoundError("Заявка не найдена")
        new_tech_id = fields.get("technician_id", current.technician_id)
        new_status = fields.get("status", current.status)
        if (
            new_tech_id is not None
            and current.technician_id is None
            and new_status == ServiceRequestStatus.PENDING
        ):
            new_status = ServiceRequestStatus.ASSIGNED
        if new_tech_id is not None and self._technicians.get_by_id(new_tech_id) is None:
            raise NotFoundError("Техник не найден")
        old_tech_id = current.technician_id
        updated = e.ServiceRequest(
            id=current.id,
            lift_id=current.lift_id,
            reason=fields.get("reason", current.reason),
            status=new_status,
            technician_id=new_tech_id,
        )
        result = self._requests.update(updated)
        assert result is not None
        self._sync_technician_status(old_tech_id, new_tech_id, current.status, new_status)
        return result

    def _sync_technician_status(
        self,
        old_tid: int | None,
        new_tid: int | None,
        old_status: ServiceRequestStatus,
        new_status: ServiceRequestStatus,
    ) -> None:
        assigned_states = {
            ServiceRequestStatus.ASSIGNED,
            ServiceRequestStatus.IN_PROGRESS,
        }
        terminal = {ServiceRequestStatus.COMPLETED, ServiceRequestStatus.CANCELLED}

        if old_tid is not None and old_tid != new_tid:
            t = self._technicians.get_by_id(old_tid)
            if t is not None and old_status in assigned_states:
                self._technicians.update(
                    e.Technician(id=t.id, name=t.name, status=TechnicianStatus.FREE)
                )

        if new_tid is not None and new_status in assigned_states:
            t = self._technicians.get_by_id(new_tid)
            if t is not None:
                self._technicians.update(
                    e.Technician(id=t.id, name=t.name, status=TechnicianStatus.BUSY)
                )
        elif new_tid is not None and new_status in terminal:
            t = self._technicians.get_by_id(new_tid)
            if t is not None:
                self._technicians.update(
                    e.Technician(id=t.id, name=t.name, status=TechnicianStatus.FREE)
                )

    def delete(self, rid: int) -> None:
        if not self._requests.delete(rid):
            raise NotFoundError("Заявка не найдена")


class TechnicianApplicationService:
    def __init__(self, tech: r.TechnicianRepository) -> None:
        self._tech = tech

    def get(self, tid: int) -> e.Technician:
        t = self._tech.get_by_id(tid)
        if t is None:
            raise NotFoundError("Техник не найден")
        return t

    def list_page(self, skip: int, limit: int) -> tuple[list[e.Technician], int]:
        return self._tech.list_paginated(skip, limit)

    def create(self, tech: e.Technician) -> e.Technician:
        return self._tech.create(tech)

    def update(self, tid: int, **fields) -> e.Technician:
        current = self._tech.get_by_id(tid)
        if current is None:
            raise NotFoundError("Техник не найден")
        updated = e.Technician(
            id=current.id,
            name=fields.get("name", current.name),
            status=fields.get("status", current.status),
        )
        result = self._tech.update(updated)
        assert result is not None
        return result

    def delete(self, tid: int) -> None:
        if not self._tech.delete(tid):
            raise NotFoundError("Техник не найден")


class ReportApplicationService:
    def __init__(
        self,
        requests: r.ServiceRequestRepository,
        lifts: r.LiftRepository,
        technicians: r.TechnicianRepository,
        reports: r.ReportRepository,
    ) -> None:
        self._requests = requests
        self._lifts = lifts
        self._technicians = technicians
        self._reports = reports

    def get(self, report_id: int) -> e.Report:
        rep = self._reports.get_by_id(report_id)
        if rep is None:
            raise NotFoundError("Отчёт не найден")
        return rep

    def list_page(self, skip: int, limit: int) -> tuple[list[e.Report], int]:
        return self._reports.list_paginated(skip, limit)

    def create(self, report: e.Report) -> e.Report:
        req = self._requests.get_by_id(report.service_request_id)
        if req is None:
            raise NotFoundError("Заявка не найдена")
        lift = self._lifts.get_by_id(req.lift_id)
        if lift is None:
            raise NotFoundError("Лифт не найден")
        created = self._reports.create(report)
        self._requests.update(
            e.ServiceRequest(
                id=req.id,
                lift_id=req.lift_id,
                reason=req.reason,
                status=ServiceRequestStatus.COMPLETED,
                technician_id=req.technician_id,
            )
        )
        self._lifts.update(
            e.Lift(
                id=lift.id,
                model=lift.model,
                status=report.final_lift_status,
                location=lift.location,
                is_emergency=False,
            )
        )
        if req.technician_id is not None:
            tech = self._technicians.get_by_id(req.technician_id)
            if tech is not None:
                self._technicians.update(
                    e.Technician(id=tech.id, name=tech.name, status=TechnicianStatus.FREE)
                )
        return created

    def update(self, report_id: int, **fields) -> e.Report:
        current = self._reports.get_by_id(report_id)
        if current is None:
            raise NotFoundError("Отчёт не найден")
        updated = e.Report(
            id=current.id,
            service_request_id=current.service_request_id,
            work_description=fields.get("work_description", current.work_description),
            final_lift_status=fields.get("final_lift_status", current.final_lift_status),
            created_at=current.created_at,
        )
        result = self._reports.update(updated)
        assert result is not None
        return result

    def delete(self, report_id: int) -> None:
        if not self._reports.delete(report_id):
            raise NotFoundError("Отчёт не найден")
