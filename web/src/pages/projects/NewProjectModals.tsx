import { Alert, Button, Code, Group, Modal, Stack, Text, TextInput, Textarea } from "@mantine/core";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCreateFromScratch, useOpenFolder } from "../../api/projects";
import { FolderPicker } from "../../components/FolderPicker";
import { folderName, joinPath } from "./projectLabels";

type ModalProps = { opened: boolean; onClose: () => void };

/** A folder that already exists becomes a project (its code stays where it is). */
export function OpenFolderModal({ opened, onClose }: ModalProps) {
  const navigate = useNavigate();
  const open = useOpenFolder();
  const [folder, setFolder] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const submit = () =>
    open.mutate(
      { folder, name: name.trim(), description: description.trim() },
      {
        onSuccess: (project) => {
          close();
          navigate(`/projects/${encodeURIComponent(project.name)}`);
        },
      },
    );
  const close = () => {
    setName("");
    setDescription("");
    open.reset();
    onClose();
  };

  return (
    <Modal opened={opened} onClose={close} title="Apri cartella" size="lg">
      <Stack>
        <FolderPicker label="Cartella del progetto" value={folder} onChange={setFolder} />
        <TextInput
          label="Nome"
          placeholder={folderName(folder)}
          description="Vuoto = nome della cartella."
          value={name}
          onChange={(event) => setName(event.currentTarget.value)}
        />
        <Textarea label="Descrizione" autosize minRows={2} value={description} onChange={(event) => setDescription(event.currentTarget.value)} />
        {open.error && <Alert color="red">{open.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>
            Annulla
          </Button>
          <Button onClick={submit} loading={open.isPending} disabled={!folder}>
            Apri come progetto
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

/** A new folder, created where you choose, becomes a project. */
export function CreateProjectModal({ opened, onClose }: ModalProps) {
  const navigate = useNavigate();
  const create = useCreateFromScratch();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [parent, setParent] = useState("");
  const [folder, setFolder] = useState("");
  const finalFolder = folder.trim() || name.trim();

  const submit = () =>
    create.mutate(
      { name: name.trim(), parent, folder_name: finalFolder, description: description.trim() },
      {
        onSuccess: (project) => {
          close();
          navigate(`/projects/${encodeURIComponent(project.name)}`);
        },
      },
    );
  const close = () => {
    setName("");
    setDescription("");
    setFolder("");
    create.reset();
    onClose();
  };

  return (
    <Modal opened={opened} onClose={close} title="Crea da zero" size="lg">
      <Stack>
        <TextInput label="Nome" required value={name} onChange={(event) => setName(event.currentTarget.value)} />
        <Textarea label="Descrizione" autosize minRows={2} value={description} onChange={(event) => setDescription(event.currentTarget.value)} />
        <FolderPicker label="Dove crearlo" value={parent} onChange={setParent} />
        <TextInput
          label="Nome della cartella"
          placeholder={name.trim() || "nuovo-progetto"}
          description="Vuoto = nome del progetto."
          value={folder}
          onChange={(event) => setFolder(event.currentTarget.value)}
        />
        {finalFolder && parent && (
          <Text size="sm">
            Verrà creata: <Code>{joinPath(parent, finalFolder)}</Code>
          </Text>
        )}
        {create.error && <Alert color="red">{create.error.message}</Alert>}
        <Group justify="flex-end">
          <Button variant="default" onClick={close}>
            Annulla
          </Button>
          <Button onClick={submit} loading={create.isPending} disabled={!name.trim() || !parent}>
            Crea progetto
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}
