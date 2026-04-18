"""
Database seeder — populates OpsMind with sample data for development.

Run:
  cd backend && python ../infra/scripts/seed_db.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../backend"))

from app.core.security import hash_password
from app.db.base import Base
from app.db.models.course import Course, CourseDomain, DifficultyLevel, Module
from app.db.models.lab import Lab, LabEnvironment, LabTask
from app.db.models.user import User, UserRole
from app.db.session import AsyncSessionLocal, engine


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        # Admin user
        admin = User(
            email="admin@opsmind.io",
            username="admin",
            hashed_password=hash_password("Admin123!"),
            full_name="OpsMind Admin",
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        db.add(admin)

        # Sample learner
        user = User(
            email="learner@opsmind.io",
            username="devlearner",
            hashed_password=hash_password("Learn123!"),
            full_name="Dev Learner",
            role=UserRole.USER,
            is_active=True,
        )
        db.add(user)

        # Kubernetes Course
        k8s_course = Course(
            title="Kubernetes in Practice",
            slug="kubernetes-in-practice",
            description="Master Kubernetes from fundamentals to production deployments.",
            domain=CourseDomain.KUBERNETES,
            difficulty=DifficultyLevel.INTERMEDIATE,
            is_published=True,
            estimated_hours=12,
        )
        db.add(k8s_course)
        await db.flush()

        modules = [
            Module(course_id=k8s_course.id, title="Pods and Deployments", order=1,
                   content_md="## Pods\nA Pod is the smallest deployable unit...\n\n```yaml\napiVersion: v1\nkind: Pod\n```",
                   is_published=True),
            Module(course_id=k8s_course.id, title="Services and Networking", order=2,
                   content_md="## Services\nServices expose your Pods...", is_published=True),
            Module(course_id=k8s_course.id, title="ConfigMaps and Secrets", order=3,
                   content_md="## Configuration Management", is_published=True),
        ]
        db.add_all(modules)

        # Lab: Deploy Nginx on K8s
        nginx_lab = Lab(
            title="Deploy Nginx on Kubernetes",
            slug="deploy-nginx-k8s",
            description="Learn to deploy, scale, and expose a web application on Kubernetes.",
            instructions_md="""# Deploy Nginx on Kubernetes

## Objective
Deploy an Nginx web server on Kubernetes and expose it via a Service.

## Tasks
1. Create a Deployment with 2 replicas of `nginx:latest`
2. Expose it using a ClusterIP Service on port 80
3. Scale it to 3 replicas
4. Verify all pods are running

## Tips
- Use `kubectl create deployment` or write a YAML manifest
- Use `kubectl expose` to create the Service
- Use `kubectl scale` to scale the deployment
""",
            image="opsmind/lab-k8s:latest",
            environment=LabEnvironment.DOCKER,
            cpu_limit="500m",
            memory_limit="512Mi",
            timeout_seconds=3600,
        )
        db.add(nginx_lab)
        await db.flush()

        tasks = [
            LabTask(
                lab_id=nginx_lab.id,
                title="Deployment exists with correct image",
                description="A Deployment named 'nginx-app' using nginx:latest must exist",
                order=1,
                points=25,
                check_script="kubectl get deployment nginx-app -o jsonpath='{.spec.template.spec.containers[0].image}' | grep -q nginx",
            ),
            LabTask(
                lab_id=nginx_lab.id,
                title="Service exposes port 80",
                description="A Service named 'nginx-svc' on port 80 must exist",
                order=2,
                points=25,
                check_script="kubectl get svc nginx-svc -o jsonpath='{.spec.ports[0].port}' | grep -q 80",
            ),
            LabTask(
                lab_id=nginx_lab.id,
                title="Deployment scaled to 3 replicas",
                order=3,
                points=25,
                check_script="kubectl get deployment nginx-app -o jsonpath='{.spec.replicas}' | grep -q 3",
            ),
            LabTask(
                lab_id=nginx_lab.id,
                title="All pods are Running",
                order=4,
                points=25,
                check_script="[ $(kubectl get pods -l app=nginx-app --field-selector=status.phase=Running --no-headers | wc -l) -ge 3 ]",
            ),
        ]
        db.add_all(tasks)

        await db.commit()
        print("✓ Database seeded successfully")
        print("  Admin: admin@opsmind.io / Admin123!")
        print("  User:  learner@opsmind.io / Learn123!")


if __name__ == "__main__":
    asyncio.run(seed())
